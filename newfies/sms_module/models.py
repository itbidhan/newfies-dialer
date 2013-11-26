#
# Newfies-Dialer License
# http://www.newfies-dialer.org
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2011-2012 Star2Billing S.L.
#
# The Initial Developer of the Original Code is
# Arezqui Belaid <info@star2billing.com>
#

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse
from django.core.cache import cache
from django.db.models.signals import post_save
from dateutil.relativedelta import relativedelta
from dialer_contact.models import Phonebook, Contact
from dialer_contact.constants import CONTACT_STATUS
from dialer_campaign.models import common_contact_authorization
from user_profile.models import UserProfile
from sms.models import Message
from sms.models import Gateway
from constants import SMS_CAMPAIGN_STATUS, SMS_SUBSCRIBER_STATUS
from datetime import datetime
from common.intermediate_model_base_class import Model
from common.common_functions import get_unique_code


class SMSCampaignManager(models.Manager):
    """SMSCampaign Manager"""

    def get_running_sms_campaign(self):
        """Return all the active smscampaigns which will be running based on
        the expiry date, the daily start/stop time and days of the week"""
        kwargs = {}
        kwargs['status'] = SMS_CAMPAIGN_STATUS.START
        tday = datetime.now()
        kwargs['startingdate__lte'] = datetime(tday.year, tday.month,
            tday.day, tday.hour, tday.minute, tday.second, tday.microsecond)
        kwargs['expirationdate__gte'] = datetime(tday.year, tday.month,
            tday.day, tday.hour, tday.minute, tday.second, tday.microsecond)

        s_time = str(tday.hour) + ":" + str(tday.minute) + ":" + str(tday.second)
        kwargs['daily_start_time__lte'] = datetime.strptime(s_time, '%H:%M:%S')
        kwargs['daily_stop_time__gte'] = datetime.strptime(s_time, '%H:%M:%S')

        # weekday status 1 - YES
        # self.model._meta.get_field(tday.strftime("%A").lower()).value()
        kwargs[tday.strftime("%A").lower()] = 1

        return SMSCampaign.objects.filter(**kwargs)

    def get_expired_sms_campaign(self):
        """Return all the smscampaigns which are expired or going to expire
         based on the expiry date but status is not 'END'"""
        kwargs = {}
        kwargs['expirationdate__lte'] = datetime.now()
        return SMSCampaign.objects.filter(**kwargs).exclude(status=SMS_CAMPAIGN_STATUS.END)


class SMSCampaign(Model):
    """This defines the SMSCampaign

    **Attributes**:

        * ``campaign_code`` - Auto-generated campaign code to identify the campaign
        * ``name`` - Campaign name
        * ``description`` - Description about the Campaign
        * ``status`` - Campaign status
        * ``callerid`` - Caller ID
        * ``startingdate`` - Starting date of the Campaign
        * ``expirationdate`` - Expiry date of the Campaign
        * ``daily_start_time`` - Start time
        * ``daily_stop_time`` - End time
        * ``week_day_setting`` (monday, tuesday, wednesday, thursday, friday, \
        saturday, sunday)
        * ``frequency`` - Frequency, speed of the campaign. number of calls/min
        * ``maxretry`` - Max retry allowed per user
        * ``intervalretry`` - Time to wait between retries in seconds
        * ``aleg_gateway`` - Gateway to use to reach the contact
        * ``extra_data`` - Additional data to pass to the application

    **Relationships**:

        * ``content_type`` - Defines the application (``voice_app`` or ``survey``) \
        to use when the call is established on the A-Leg

        * ``object_id`` - Defines the object of content_type application

        * ``content_object`` - Used to define the Voice App or the Survey with generic ForeignKey

        * ``phonebook`` - Many-To-Many relationship to the Phonebook model.

        * ``user`` - Foreign key relationship to the a User model. \
        Each campaign assigned to a User

    **Name of DB table**: sms_campaign
    """
    campaign_code = models.CharField(unique=True, max_length=20, blank=True,
                                     verbose_name=_("SMS campaign code"),
                                     help_text=_('this code is auto-generated by the platform, \
                                     this is used to identify the campaign'),
                                     default=(lambda: get_unique_code(length=5)))

    name = models.CharField(max_length=100, verbose_name=_('name'))
    description = models.TextField(verbose_name=_('description'), blank=True,
                                   null=True, help_text=_("campaign description"))
    user = models.ForeignKey('auth.User', related_name='SMSCampaign owner')
    status = models.IntegerField(choices=list(SMS_CAMPAIGN_STATUS), blank=True, null=True,
                                 default=SMS_CAMPAIGN_STATUS.PAUSE, verbose_name=_("status"))
    callerid = models.CharField(max_length=80, blank=True,
                                verbose_name=_("callerID"),
                                help_text=_("outbound caller-ID"))
    #General Starting & Stopping date
    startingdate = models.DateTimeField(
        default=(lambda: datetime.now()), verbose_name=_('start'),
        help_text=_("date format: YYYY-mm-DD HH:MM:SS"))

    expirationdate = models.DateTimeField(
        default=(lambda: datetime.now() + relativedelta(months=+1)),
        verbose_name=_('finish'), help_text=_("date format: YYYY-mm-DD HH:MM:SS"))
    #Per Day Starting & Stopping Time
    daily_start_time = models.TimeField(default='00:00:00', help_text=_("time format: HH:MM:SS"))
    daily_stop_time = models.TimeField(default='23:59:59', help_text=_("time format: HH:MM:SS"))
    monday = models.BooleanField(default=True, verbose_name=_('monday'))
    tuesday = models.BooleanField(default=True, verbose_name=_('tuesday'))
    wednesday = models.BooleanField(default=True, verbose_name=_('wednesday'))
    thursday = models.BooleanField(default=True, verbose_name=_('thursday'))
    friday = models.BooleanField(default=True, verbose_name=_('friday'))
    saturday = models.BooleanField(default=True, verbose_name=_('saturday'))
    sunday = models.BooleanField(default=True, verbose_name=_('sunday'))
    #Campaign Settings
    frequency = models.IntegerField(default='10', blank=True, null=True,
                                    verbose_name=_('frequency'),
                                    help_text=_("SMS per minute"))

    maxretry = models.IntegerField(default='0', blank=True, null=True,
                                   verbose_name=_('max retries'),
                                   help_text=_("maximum retries per contact"))
    intervalretry = models.IntegerField(
        default='300', blank=True, null=True, verbose_name=_('time between Retries'),
        help_text=_("time delay in seconds before retrying contact"))

    sms_gateway = models.ForeignKey(Gateway, verbose_name=_("sms gateway"),
                                    related_name="SMS Gateway",
                                    help_text=_("select outbound gateway"))
    text_message = models.TextField(verbose_name=_('text Message'), blank=True,
                                    null=True, help_text=_("content of the SMS"))

    extra_data = models.CharField(max_length=120, blank=True,
                                  verbose_name=_("extra parameters"),
                                  help_text=_("additional application parameters."))

    created_date = models.DateTimeField(auto_now_add=True, verbose_name='Date')
    updated_date = models.DateTimeField(auto_now=True)

    phonebook = models.ManyToManyField(Phonebook, blank=True, null=True)

    imported_phonebook = models.CharField(max_length=500, default='',
                                          verbose_name=_('list of imported phonebook'))
    totalcontact = models.IntegerField(default=0, blank=True, null=True,
                                       verbose_name=_('total contact'),
                                       help_text=_("total contact for this campaign"))

    objects = SMSCampaignManager()

    def __unicode__(self):
        return u"%s" % (self.name)

    class Meta:
        permissions = (
            ("view_smscampaign", _('can see SMS campaign')),
            ("view_sms_dashboard", _('can see SMS campaign dashboard'))
        )
        db_table = u'sms_campaign'
        verbose_name = _("SMS campaign")
        verbose_name_plural = _("SMS campaigns")

    def update_sms_campaign_status(self):
        """Update the sms_campaign's status

        For example,
        If campaign is active, you can change status to 'Pause' or 'Stop'
        """
        # active - 1 | pause - 2 | abort - 3 | stop - 4
        if self.status == SMS_CAMPAIGN_STATUS.START:
            return "<a href='%s'>Pause</a> | <a href='%s'>Abort</a> | <a href='%s'>Stop</a>" % (
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.PAUSE]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.ABORT]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.END]))

        if self.status == SMS_CAMPAIGN_STATUS.PAUSE:
            return "<a href='%s'>Start</a> | <a href='%s'>Abort</a> | <a href='%s'>Stop</a>" % (
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.START]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.ABORT]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.END]))

        if self.status == SMS_CAMPAIGN_STATUS.ABORT:
            return "<a href='%s'>Start</a> | <a href='%s'>Pause</a> | <a href='%s'>Stop</a>" % (
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.START]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.PAUSE]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.END]))

        if self.status == SMS_CAMPAIGN_STATUS.END:
            return "<a href='%s'>Start</a> | <a href='%s'>Pause</a> | <a href='%s'>Abort</a>" % (
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.START]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.PAUSE]),
                reverse('sms_module.views.update_sms_campaign_status_admin', args=[self.pk, SMS_CAMPAIGN_STATUS.ABORT]))

    update_sms_campaign_status.allow_tags = True
    update_sms_campaign_status.short_description = _('action')

    def count_contact_of_phonebook(self, status=None):
        """Count the no. of Contacts in a phonebook"""
        if status == CONTACT_STATUS.ACTIVE:
            count_contact = Contact.objects.filter(
                status=CONTACT_STATUS.ACTIVE,
                phonebook__smscampaign=self.id).count()
        else:
            count_contact = Contact.objects.filter(
                phonebook__smscampaign=self.id).count()
        if not count_contact:
            return _("Phonebook Empty")
        return count_contact
    count_contact_of_phonebook.allow_tags = True
    count_contact_of_phonebook.short_description = _('contact')

    def is_authorized_contact(self, str_contact):
        """Check if a contact is authorized"""
        try:
            dialersetting = UserProfile.objects.get(user=self.user).dialersetting
            return common_contact_authorization(dialersetting, str_contact)
        except UserProfile.DoesNotExist:
            return False

    def get_active_max_frequency(self):
        """Get the active max frequency"""
        try:
            sms_dialersetting = UserProfile.objects.get(user=self.user).dialersetting
        except UserProfile.DoesNotExist:
            return self.frequency

        # sms_max_frequency
        max_frequency = sms_dialersetting.sms_max_frequency
        if max_frequency < self.frequency:
            return max_frequency

        return self.frequency

    def get_active_contact(self):
        """Get all the active Contacts from the phonebook"""
        list_contact = Contact.objects.filter(
            phonebook__smscampaign=self.id,
            status=CONTACT_STATUS.ACTIVE).all()
        if not list_contact:
            return False
        return list_contact

    def get_active_contact_no_subscriber(self):
        """List of active contacts that do not exist in Campaign Subscriber"""
        # The list of active contacts that doesn't
        # exist in SMSCampaignSubscriber

        #TODO : This might kill performance on huge phonebook...
        query = \
            'SELECT dc.id, dc.phonebook_id, dc.contact, dc.last_name, \
            dc.first_name, dc.email, dc.city, dc.description, \
            dc.status, dc.additional_vars, dc.created_date, dc.updated_date \
            FROM dialer_contact as dc \
            INNER JOIN dialer_phonebook ON \
            (dc.phonebook_id = dialer_phonebook.id) \
            INNER JOIN sms_campaign_phonebook ON \
            (dialer_phonebook.id = sms_campaign_phonebook.phonebook_id) \
            WHERE sms_campaign_phonebook.smscampaign_id = %s \
            AND dc.status = 1 \
            AND dc.id NOT IN \
            (SELECT  sms_campaign_subscriber.contact_id \
            FROM sms_campaign_subscriber \
            WHERE sms_campaign_subscriber.sms_campaign_id = %s)' % \
            (str(self.id), str(self.id),)

        raw_contact_list = Contact.objects.raw(query)
        return raw_contact_list

    def progress_bar(self):
        """Progress bar generated based on no of contacts"""
        # Cache campaignsubscriber_count
        count_contact = Contact.objects.filter(phonebook__smscampaign=self.id).count()

        # Cache need to be set per campaign
        # sms_campaignsubscriber_count_key_campaign_id_1
        sms_campaignsubscriber_count = cache.get(
            'sms_campaignsubscriber_count_key_campaign_id_' + str(self.id))
        #sms_campaignsubscriber_count = None
        if sms_campaignsubscriber_count is None:
            list_contact = Contact.objects.values_list('id', flat=True)\
                .filter(phonebook__smscampaign=self.id)
            sms_campaignsubscriber_count = 0

            try:
                sms_campaignsubscriber_count += SMSCampaignSubscriber.objects.filter(
                    contact__in=list_contact, sms_campaign=self.id,
                    status=SMS_SUBSCRIBER_STATUS.COMPLETE).count()
            except:
                pass

            cache.set("sms_campaignsubscriber_count_key_campaign_id_" + str(self.id),
                      sms_campaignsubscriber_count, 5)

        sms_campaignsubscriber_count = int(sms_campaignsubscriber_count)
        count_contact = int(count_contact)

        if count_contact > 0:
            percentage_pixel = (float(sms_campaignsubscriber_count) / count_contact) * 100
            percentage_pixel = int(percentage_pixel)
        else:
            percentage_pixel = 0
        sms_campaignsubscriber_count_string = "sms_campaign-subscribers (" + \
            str(sms_campaignsubscriber_count) + ")"
        return "<div title='%s' style='width: 100px; border: 1px solid #ccc;'>\
                <div style='height: 4px; width: %dpx; background: #555; '>\
                </div></div>" % (sms_campaignsubscriber_count_string, percentage_pixel)
    progress_bar.allow_tags = True
    progress_bar.short_description = _('progress')

    def sms_campaignsubscriber_detail(self):
        """This will link to sms_campaign subscribers who are associated with
        the sms_campaign"""
        model_name = SMSCampaignSubscriber._meta.object_name.lower()
        app_label = self._meta.app_label
        link = '/admin/%s/%s/' % (app_label, model_name)
        link += '?sms_campaign__id=%d' % self.id
        display_link = _("<a href='%(link)s'>%(name)s</a>") %\
            {'link': link, 'name': _('details')}
        return display_link
    sms_campaignsubscriber_detail.allow_tags = True
    sms_campaignsubscriber_detail.short_description = _('SMSCampaign Subscriber')

    def get_pending_subscriber(self, limit=1000):
        """Get all the pending subscribers from the sms_campaign"""
        list_subscriber = SMSCampaignSubscriber.objects.filter(
            sms_campaign=self.id, status=SMS_SUBSCRIBER_STATUS.PENDING)\
            .all()[:limit]
        if not list_subscriber:
            return False
        return list_subscriber

    def get_pending_subscriber_update(self, limit=1000, status=6):
        """Get all the pending subscribers from the campaign"""
        # TODO in django 1.4 : replace by SELECT FOR UPDATE
        list_subscriber = SMSCampaignSubscriber.objects.filter(
            sms_campaign=self.id, status=SMS_SUBSCRIBER_STATUS.PENDING)\
            .all()[:limit]
        if not list_subscriber:
            return False
        for elem_subscriber in list_subscriber:
            elem_subscriber.status = status
            elem_subscriber.save()
        return list_subscriber


class SMSCampaignSubscriber(Model):
    """This defines the Contact imported to a SMSCampaign

    **Attributes**:

        * ``last_attempt`` -
        * ``count_attempt`` -
        * ``duplicate_contact`` -
        * ``status`` -

    **Relationships**:

        * ``contact`` - Foreign key relationship to the Contact model.
        * ``campaign`` - Foreign key relationship to the Campaign model.

    **Name of DB table**: sms_campaign_subscriber
    """
    message = models.ForeignKey(Message, null=True, blank=True,
                                help_text=_("select message"))
    contact = models.ForeignKey(Contact, null=True, blank=True,
                                help_text=_("select contact"))
    sms_campaign = models.ForeignKey(SMSCampaign, null=True, blank=True,
                                     help_text=_("select SMS campaign"))
    last_attempt = models.DateTimeField(null=True, blank=True,
                                        verbose_name=_("last attempt"))
    count_attempt = models.IntegerField(null=True, blank=True, default='0',
                                        verbose_name=_("count attempts"))
    #We duplicate contact to create a unique constraint
    duplicate_contact = models.CharField(max_length=90,
                                         verbose_name=_("contact"))
    status = models.IntegerField(choices=list(SMS_SUBSCRIBER_STATUS),
                                 default=SMS_SUBSCRIBER_STATUS.PENDING,
                                 blank=True, null=True, verbose_name=_("status"),
                                 db_index=True)

    created_date = models.DateTimeField(auto_now_add=True, verbose_name='Date')
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = u'sms_campaign_subscriber'
        verbose_name = _("SMS campaign subscriber")
        verbose_name_plural = _("SMS campaign subscribers")
        unique_together = ['contact', 'sms_campaign']

    def __unicode__(self):
            return u"%s" % str(self.id)

    def contact_name(self):
        return self.contact.first_name

    # static method to perform a stored procedure
    # Ref link - http://www.chrisumbel.com/article/django_python_stored_procedures.aspx
    """
    @staticmethod
    def importcontact_pl_sql(campaign_id, phonebook_id):
        # create a cursor
        from django.db import connection
        cur = connection.cursor()

        # execute the stored procedure passing in
        # campaign_id, phonebook_id as a parameter
        cur.callproc('importcontact_pl_sql', [campaign_id, phonebook_id])

        cur.close()
        return True
    """


class SMSMessage(Message):
    """extension on Message

    **Attributes**:


    **Relationships**:

        * ``message`` - One to one relationship to the Message model.
        * ``sms_campaign`` - Foreign key relationship to the SMSCampaign model.

    **Name of DB table**: message_smscampaign
    """
    message = models.OneToOneField(Message)
    sms_campaign = models.ForeignKey(SMSCampaign, null=True, blank=True,
                                     help_text=_("select SMS campaign"))

    class Meta:
        permissions = (
            ("view_sms_report", _('can see SMS report')),
        )
        db_table = u'smsmessage'
        verbose_name = _("SMS message")
        verbose_name_plural = _("SMS messages")


def post_save_add_contact(sender, **kwargs):
    """A ``post_save`` signal is sent by the Contact model instance whenever
    it is going to save.

    **Logic Description**:

        * When new contact is added into ``Contact`` model, active the
          campaign list will be checked with the contact status.
        * If the active campaign list count is more than one & the contact
          is active, the contact will be added into ``SMSCampaignSubscriber``
          model.
    """
    obj = kwargs['instance']
    active_campaign_list = SMSCampaign.objects.filter(
        phonebook__contact__id=obj.id, status=SMS_CAMPAIGN_STATUS.START)
    # created instance = True + active contact + active_campaign
    if kwargs['created'] and obj.status == SMS_CAMPAIGN_STATUS.START and active_campaign_list.count() >= 1:
        for elem_campaign in active_campaign_list:
            try:
                SMSCampaignSubscriber.objects.create(
                    contact=obj,
                    duplicate_contact=obj.contact,
                    status=SMS_CAMPAIGN_STATUS.START,  # START
                    sms_campaign=elem_campaign)
            except:
                pass

post_save.connect(post_save_add_contact, sender=Contact)
