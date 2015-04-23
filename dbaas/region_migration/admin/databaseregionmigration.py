# -*- coding: utf-8 -*-
import logging
from django_services import admin
from django.utils.html import format_html
from django.core.urlresolvers import reverse
from django.conf.urls import url, patterns
from django.http import HttpResponseRedirect
from datetime import datetime
from notification.models import TaskHistory
from ..models import DatabaseRegionMigration
from ..models import DatabaseRegionMigrationDetail
from ..service.databaseregionmigration import DatabaseRegionMigrationService
from ..tasks import execute_database_region_migration
from django.shortcuts import render_to_response
from django.template import RequestContext
from ..forms import DatabaseRegionMigrationDetailForm

LOG = logging.getLogger(__name__)


class DatabaseRegionMigrationAdmin(admin.DjangoServicesAdmin):
    model = DatabaseRegionMigration
    list_display = ('database', 'steps_information', 'status',
                    'description', 'user_friendly_warning',
                    'schedule_next_step_html')

    actions = None
    service_class = DatabaseRegionMigrationService
    list_display_links = ()
    template = 'region_migration/databaseregionmigration/schedule_next_step.html'

    def __init__(self, *args, **kwargs):
        super(DatabaseRegionMigrationAdmin, self).__init__(*args, **kwargs)
        self.list_display_links = (None, )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def schedule_next_step_html(self, databaseregionmigration):
        id = databaseregionmigration.id
        current_step = databaseregionmigration.current_step
        last_step = len(databaseregionmigration.get_steps()) - 1

        is_migration_finished = current_step == last_step

        waiting_status = DatabaseRegionMigrationDetail.WAITING
        running_status = DatabaseRegionMigrationDetail.RUNNING

        migration_running_or_waiting = DatabaseRegionMigrationDetail.objects.\
            filter(database_region_migration=databaseregionmigration,
                   status__in=[waiting_status, running_status])

        if is_migration_finished or migration_running_or_waiting:
            return ''

        html = "<a class='btn btn-info' href='{}/schedulenextstep/'><i\
                class='icon-chevron-right icon-white'></i></a>".format(id)

        return format_html(html)

    schedule_next_step_html.short_description = "Schedule next step"

    def user_friendly_warning(self, databaseregionmigration):
        warning_message = databaseregionmigration.warning

        if warning_message:
            html = '<span class="label label-warning"><font size=3.5>\
                    {}</font></span>'.format(warning_message)
            return format_html(html)

        return warning_message

    user_friendly_warning.short_description = "Warning"

    def steps_information(self, databaseregionmigration):
        current_step = str(databaseregionmigration.current_step)
        steps_len = str(len(databaseregionmigration.get_steps()))
        information = '{} of {}'.format(current_step, steps_len)

        return information

    steps_information.short_description = "Current Step"

    def get_urls(self):
        urls = super(DatabaseRegionMigrationAdmin, self).get_urls()
        my_urls = patterns('',
                           url(r'^/?(?P<databaseregionmigration_id>\d+)/schedulenextstep/$',
                               self.admin_site.admin_view(self.databaseregionmigration_view)),
                           )
        return my_urls + urls

    def databaseregionmigration_view(self, request, databaseregionmigration_id):
        form = DatabaseRegionMigrationDetailForm
        database_region_migration = DatabaseRegionMigration.objects.get(id=databaseregionmigration_id)
        add = True

        if request.method == 'POST':
            form = DatabaseRegionMigrationDetailForm(request.POST)
            if form.is_valid():
                scheduled_for = form.cleaned_data['scheduled_for']

                database_region_migration_detail = DatabaseRegionMigrationDetail(
                    database_region_migration=database_region_migration,
                    step=database_region_migration.current_step,
                    scheduled_for=scheduled_for,
                    created_by=request.user.username)

                database_region_migration_detail.save()

                task_history = TaskHistory()
                task_history.task_name = "execute_database_region_migration"
                task_history.task_status = task_history.STATUS_WAITING

                description = database_region_migration.description
                task_history.arguments = "Database name: {}, \
                                          Step: {}".format(database_region_migration.database.name, description)
                task_history.user = request.user
                task_history.save()
                execute_database_region_migration.apply_async(args=[database_region_migration_detail.id,
                                                              task_history, request.user],
                                                              eta=scheduled_for)

                url = reverse('admin:notification_taskhistory_changelist')
                return HttpResponseRedirect(url + "?user=%s" % request.user.username)

        return render_to_response("region_migration/databaseregionmigrationdetail/schedule_next_step.html",
                                  locals(),
                                  context_instance=RequestContext(request))