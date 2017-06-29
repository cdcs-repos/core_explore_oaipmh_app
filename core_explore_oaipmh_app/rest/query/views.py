""" REST views for the explore OAI-PMH  API
"""
import json

import core_oaipmh_harvester_app.components.oai_record.api as oai_record_api
from core_main_app.utils.xml import unparse
from core_oaipmh_common_app.commons.messages import OaiPmhMessage
from core_oaipmh_harvester_app.components.oai_harvester_metadata_format import api \
    as oai_harvester_metadata_format_api
from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core_explore_common_app.components.result.models import Result
from core_explore_common_app.rest.result.serializers import ResultSerializer
from core_explore_common_app.utils.pagination.rest_framework_paginator.pagination \
    import StandardResultsSetPagination
from core_explore_common_app.utils.result import result as result_utils
from core_explore_oaipmh_app.utils.query.mongo.query_builder import OaiPmhQueryBuilder


@api_view(['POST'])
def execute_query(request):
    """ Executes query and returns results.

    Args:
        request: Request.

    Returns:
        Response: Response.

    """
    try:
        # get query
        query = request.POST.get('query', None)
        options = request.POST.get('options', None)

        if query is not None:
            query_builder = OaiPmhQueryBuilder(query, 'metadata')
        else:
            return Response('Query should be passed in parameter',
                            status=status.HTTP_400_BAD_REQUEST)

        if options is not None:
            json_options = json.loads(options)
            instance_id = json_options['instance_id']
        else:
            return Response('Missing instance information.', status=status.HTTP_400_BAD_REQUEST)

        # update the content query with given templates
        if 'templates' in request.POST:
            templates = json.loads(request.POST['templates'])
            if len(templates) > 0:
                # get list of template ids
                list_template_ids = [template['id'] for template in templates]
                # get all metadata formats used by the instance (registry)
                list_metadata_format = oai_harvester_metadata_format_api.\
                    get_all_by_registry_id(instance_id)
                # Filter metadata formats that use the given templates
                list_metadata_formats_id = [str(x.id) for x in list_metadata_format
                                            if x.template is not None
                                            and str(x.template.id) in list_template_ids]
                query_builder.add_list_metadata_formats_criteria(list_metadata_formats_id)

        # create a raw query
        raw_query = query_builder.get_raw_query()
        # execute query
        data_list = oai_record_api.execute_query(raw_query)
        # get paginator
        paginator = StandardResultsSetPagination()
        # get requested page from list of results
        page = paginator.paginate_queryset(data_list, request)

        # Serialize object
        results = []
        url = reverse("core_explore_oaipmh_app_data_detail")
        url_access_data = reverse("core_explore_oaipmh_app_rest_get_result_from_data_id")
        # Template info
        template_info = dict()
        for data in page:
            # get data's template
            template = data.harvester_metadata_format.template
            # get and store data's template information
            if template not in template_info:
                template_info[template] = result_utils.get_template_info(template)

            results.append(Result(title=data.identifier,
                                  xml_content=unparse(data.metadata),
                                  template_info=template_info[template],
                                  detail_url="{0}?id={1}".format(url, data.id),
                                  access_data_url="{0}?id={1}".format(url_access_data,
                                                                      str(data.id))))

        # Serialize results
        serialized_results = ResultSerializer(results, many=True)
        # Return http response
        return paginator.get_paginated_response(serialized_results.data)
    except Exception as e:
        content = OaiPmhMessage.get_message_labelled('An error occurred when attempting to execute'
                                                     ' the query: %s' % e.message)
        return Response(content, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
