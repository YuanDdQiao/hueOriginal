#!/usr/bin/env python
# Licensed to Cloudera, Inc. under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  Cloudera, Inc. licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging

from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.utils.encoding import smart_str
from django.utils.translation import ugettext as _
from django.shortcuts import redirect

from desktop.lib.django_util import render
from desktop.lib.exceptions_renderable import PopupException

from search.api import SolrApi, _guess_gap, _zoom_range_facet, _new_range_facet
from search.conf import SOLR_URL
from search.data_export import download as export_download
from search.decorators import allow_admin_only
from search.management.commands import search_setup
from search.models import Collection, augment_solr_response, augment_solr_exception
from search.search_controller import SearchController

from django.utils.encoding import force_unicode
from desktop.lib.rest.http_client import RestException



LOG = logging.getLogger(__name__)


def initial_collection(request, hue_collections):
  return hue_collections[0].id


def index(request):
  hue_collections = SearchController(request.user).get_search_collections()
  collection_id = request.GET.get('collection')
  
  if not hue_collections or not collection_id:
    if request.user.is_superuser:
      return admin_collections(request, True)
    else:
      return no_collections(request)

  collection = Collection.objects.get(id=collection_id) # TODO perms HUE-1987
  query = {'qs': [{'q': ''}], 'fqs': [], 'start': 0}

  return render('search.mako', request, {
    'collection': collection,
    'query': query,
    'initial': '{}',    
  })


# TODO security
def new_search(request):
  collections = SearchController(request.user).get_solr_collection().keys()
  if not collections:
    return no_collections(request)

  collection = Collection(name=collections[0], label=collections[0])
  query = {'qs': [{'q': ''}], 'fqs': [], 'start': 0}

  return render('search.mako', request, {
    'collection': collection,
    'query': query,
    'initial': json.dumps({
         'collections': collections,
         'layout': [
              {"size":2,"rows":[{"widgets":[]}],"drops":["temp"],"klass":"card card-home card-column span2"},
              {"size":10,"rows":[{"widgets":[
                  {"size":12,"name":"Grid Results","id":"52f07188-f30f-1296-2450-f77e02e1a5c0","widgetType":"resultset-widget",
                   "properties":{},"offset":0,"isLoading":True,"klass":"card card-widget span12"}]}],
              "drops":["temp"],"klass":"card card-home card-column span10"}
         ] 
     }),
  })


# TODO security
def browse(request, name):
  collections = SearchController(request.user).get_solr_collection().keys()
  if not collections:
    return no_collections(request)

  collection = Collection(name=name, label=name)
  query = {'qs': [{'q': ''}], 'fqs': [], 'start': 0}

  return render('search.mako', request, {
    'collection': collection,
    'query': query,
    'initial': json.dumps({
         'autoLoad': True,
         'collections': collections,
         'layout': [
              {"size":12,"rows":[{"widgets":[
                  {"size":12,"name":"Grid Results","id":"52f07188-f30f-1296-2450-f77e02e1a5c0","widgetType":"resultset-widget",
                   "properties":{},"offset":0,"isLoading":True,"klass":"card card-widget span12"}]}],
              "drops":["temp"],"klass":"card card-home card-column span10"}
         ] 
     }),
  })


def search(request):
  response = {}  
  
  collection = json.loads(request.POST.get('collection', '{}')) # TODO decorator with doc model perms
  query = json.loads(request.POST.get('query', '{}'))
  # todo: remove the selected histo facet if multiq

  if collection['id']:
    hue_collection = Collection.objects.get(id=collection['id']) # TODO perms
    
  if collection:
    try:      
      response = SolrApi(SOLR_URL.get(), request.user).query(collection, query)
      response = augment_solr_response(response, collection, query)
    except RestException, e:
      try:
        response['error'] = json.loads(e.message)['error']['msg']
      except:
        response['error'] = force_unicode(str(e))
    except Exception, e:
      raise PopupException(e, title=_('Error while accessing Solr'))
      
      response['error'] = force_unicode(str(e))
  else:
    response['error'] = _('There is no collection to search.')

  if 'error' in response:
    augment_solr_exception(response, collection)

  return HttpResponse(json.dumps(response), mimetype="application/json")


def save(request):
  response = {'status': -1}  
  
  collection = json.loads(request.POST.get('collection', '{}')) # TODO perms decorator
  layout = json.loads(request.POST.get('layout', '{}')) 
    
  if collection:
    if collection['id']:
      hue_collection = Collection.objects.get(id=collection['id'])
    else:
      hue_collection = Collection.objects.create2(name=collection['name'], label=collection['label'])
    hue_collection.update_properties({'collection': collection})
    hue_collection.update_properties({'layout': layout})
    hue_collection.name = collection['name']
    hue_collection.label = collection['label']
    hue_collection.enable = collection['enabled']
    hue_collection.save()
    response['status'] = 0
    response['id'] = hue_collection.id
    response['message'] = _('Page saved !')
  else:
    response['message'] = _('There is no collection to search.')

  return HttpResponse(json.dumps(response), mimetype="application/json")


def download(request):
  try:
    file_format = 'csv' if 'csv' in request.POST else 'xls' if 'xls' in request.POST else 'json'
    response = search(request)
    
    if file_format == 'json':
      mimetype = 'application/json'
      json_docs = json.dumps(json.loads(response.content)['response']['docs'])
      resp = HttpResponse(json_docs, mimetype=mimetype)
      resp['Content-Disposition'] = 'attachment; filename=%s.%s' % ('query_result', file_format)
      return resp    
    
    return export_download(json.loads(response.content), file_format)
  except Exception, e:
    raise PopupException(_("Could not download search results: %s") % e)


def no_collections(request):
  return render('no_collections.mako', request, {})


@allow_admin_only
def admin_collections(request, is_redirect=False):
  existing_hue_collections = Collection.objects.all()

  if request.GET.get('format') == 'json':
    collections = []
    for collection in existing_hue_collections:
      massaged_collection = {
        'id': collection.id,
        'name': collection.name,
        'label': collection.label,
        'isCoreOnly': collection.is_core_only,
        'absoluteUrl': collection.get_absolute_url()
      }
      collections.append(massaged_collection)
    return HttpResponse(json.dumps(collections), mimetype="application/json")

  return render('admin_collections.mako', request, {
    'existing_hue_collections': existing_hue_collections,
    'is_redirect': is_redirect
  })



@allow_admin_only
def admin_collections_import(request):
  if request.method == 'POST':
    searcher = SearchController(request.user)
    imported = []
    not_imported = []
    status = -1
    message = ""
    importables = json.loads(request.POST["selected"])
    for imp in importables:
      try:
        searcher.add_new_collection(imp)
        imported.append(imp['name'])
      except Exception, e:
        not_imported.append(imp['name'] + ": " + unicode(str(e), "utf8"))

    if len(imported) == len(importables):
      status = 0;
      message = _('Collection(s) or core(s) imported successfully!')
    elif len(not_imported) == len(importables):
      status = 2;
      message = _('There was an error importing the collection(s) or core(s)')
    else:
      status = 1;
      message = _('Collection(s) or core(s) partially imported')

    result = {
      'status': status,
      'message': message,
      'imported': imported,
      'notImported': not_imported
    }

    return HttpResponse(json.dumps(result), mimetype="application/json")
  else:
    if request.GET.get('format') == 'json':
      searcher = SearchController(request.user)
      new_solr_collections = searcher.get_new_collections()
      massaged_collections = []
      for coll in new_solr_collections:
        massaged_collections.append({
          'type': 'collection',
          'name': coll
        })
      new_solr_cores = searcher.get_new_cores()
      massaged_cores = []
      for core in new_solr_cores:
        massaged_cores.append({
          'type': 'core',
          'name': core
        })
      response = {
        'newSolrCollections': list(massaged_collections),
        'newSolrCores': list(massaged_cores)
      }
      return HttpResponse(json.dumps(response), mimetype="application/json")
    else:
      return admin_collections(request, True)


@allow_admin_only
def admin_collection_delete(request):
  if request.method != 'POST':
    raise PopupException(_('POST request required.'))

  id = request.POST.get('id')
  searcher = SearchController(request.user)
  response = {
    'id': searcher.delete_collection(id)
  }

  return HttpResponse(json.dumps(response), mimetype="application/json")


@allow_admin_only
def admin_collection_copy(request):
  if request.method != 'POST':
    raise PopupException(_('POST request required.'))

  id = request.POST.get('id')
  searcher = SearchController(request.user)
  response = {
    'id': searcher.copy_collection(id)
  }

  return HttpResponse(json.dumps(response), mimetype="application/json")


# TODO security
def query_suggest(request, collection_id, query=""):
  hue_collection = Collection.objects.get(id=collection_id)
  result = {'status': -1, 'message': 'Error'}

  solr_query = {}
  solr_query['collection'] = hue_collection.name
  solr_query['q'] = query

  try:
    response = SolrApi(SOLR_URL.get(), request.user).suggest(solr_query, hue_collection)
    result['message'] = response
    result['status'] = 0
  except Exception, e:
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")


# TODO security
def index_fields_dynamic(request):  
  result = {'status': -1, 'message': 'Error'}
  
  try:
    name = request.POST['name']
            
    hue_collection = Collection(name=name, label=name)    
    
    dynamic_fields = SolrApi(SOLR_URL.get(), request.user).luke(hue_collection.name)

    result['message'] = ''
    result['fields'] = [Collection._make_field(name, properties)
                        for name, properties in dynamic_fields['fields'].iteritems() if 'dynamicBase' in properties]
    result['gridlayout_header_fields'] = [Collection._make_gridlayout_header_field({'name': name}, True) 
                                          for name, properties in dynamic_fields['fields'].iteritems() if 'dynamicBase' in properties]
    result['status'] = 0
  except Exception, e:
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")


# TODO security
def get_document(request):  
  result = {'status': -1, 'message': 'Error'}

  try:
    collection = json.loads(request.POST.get('collection', '{}'))
    doc_id = request.POST.get('id')
            
    if doc_id:
      result['doc'] = SolrApi(SOLR_URL.get(), request.user).get(collection['name'], doc_id)
      result['status'] = 0
      result['message'] = ''
    else:
      result['message'] = _('This document does not have any index id.')
      result['status'] = 1
    
  except Exception, e:
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")


# TODO security
def get_timeline(request):  
  result = {'status': -1, 'message': 'Error'}

  try:
    collection = json.loads(request.POST.get('collection', '{}'))
    query = json.loads(request.POST.get('query', '{}'))
    facet = json.loads(request.POST.get('facet', '{}'))
    qdata = json.loads(request.POST.get('qdata', '{}'))
    multiQ = request.POST.get('multiQ', 'query')
    
    if multiQ == 'query':
      label = qdata['q'] 
      query['qs'] = [qdata]
    elif facet['type'] == 'range':      
      _prop = filter(lambda prop: prop['from'] == qdata, facet['properties'])[0]
      label = '%(from)s - %(to)s ' % _prop
      facet_id = facet['id']
      # Only care about our current field:value filter
      for fq in query['fqs']:
        if fq['id'] == facet_id:
          fq['properties'] = [_prop]
    else:
      label = qdata
      facet_id = facet['id']
      # Only care about our current field:value filter
      for fq in query['fqs']:
        if fq['id'] == facet_id:
          fq['filter'] = [qdata] 
      
    # Remove other facets from collection for speed
    collection['facets'] = filter(lambda f: f['widgetType'] == 'histogram-widget', collection['facets'])
    
    response = SolrApi(SOLR_URL.get(), request.user).query(collection, query)
    response = augment_solr_response(response, collection, query)
  
    label += ' (%s) ' % response['response']['numFound']
  
    result['series'] = {'label': label, 'counts': response['normalized_facets'][0]['counts']}
    result['status'] = 0
    result['message'] = ''
  except Exception, e:
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")


# TODO security
def new_facet(request):  
  result = {'status': -1, 'message': 'Error'}
  
  try:
    collection = json.loads(request.POST.get('collection', '{}'))
    
    facet_id = request.POST['id']
    facet_label = request.POST['label']
    facet_field = request.POST['field']
    widget_type = request.POST['widget_type']
    properties = {
      'sort': 'desc',
      'canRange': False,
      'stacked': False,
      'limit': 10,
      'mincount': 0,
      'andUp': False,  # Not used yet
    }
    
    solr_api = SolrApi(SOLR_URL.get(), request.user)
    range_properties = _new_range_facet(solr_api, collection, facet_field, widget_type)
                          
    if range_properties:
      facet_type = 'range'
      properties.update(range_properties)       
    elif widget_type == 'hit-widget':
      facet_type = 'query'      
    else:
      facet_type = 'field'        
        
    if widget_type == 'map-widget':
      properties['scope'] = 'world'
      properties['mincount'] = 1
      properties['limit'] = 100        
        
    result['message'] = ''
    result['facet'] = {
      'id': facet_id,
      'label': facet_label,
      'field': facet_field,
      'type': facet_type,
      'widgetType': widget_type,
      'properties': properties
    }
    result['status'] = 0
  except Exception, e:
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")

# TODO security
def get_range_facet(request):  
  result = {'status': -1, 'message': 'Error'}

  try:
    collection = json.loads(request.POST.get('collection', '{}'))
    facet = json.loads(request.POST.get('facet', '{}'))
    action = request.POST.get('action', 'select')
            
    solr_api = SolrApi(SOLR_URL.get(), request.user)

    if action == 'select':
      properties = _guess_gap(solr_api, collection, facet, facet['properties']['start'], facet['properties']['end'])
    else:
      properties = _zoom_range_facet(solr_api, collection, facet)
            
    result['properties'] = properties
    result['status'] = 0      

  except Exception, e:
    print e
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")


# TODO security
def get_collection(request):  
  result = {'status': -1, 'message': 'Error'}

  try:
    name = request.POST['name']
            
    collection = Collection(name=name, label=name)
    collection_json = collection.get_c(request.user)
            
    result['collection'] = json.loads(collection_json)
    result['status'] = 0      

  except Exception, e:
    result['message'] = unicode(str(e), "utf8")

  return HttpResponse(json.dumps(result), mimetype="application/json")


def install_examples(request):
  result = {'status': -1, 'message': ''}

  if request.method != 'POST':
    result['message'] = _('A POST request is required.')
  else:
    try:
      search_setup.Command().handle_noargs()
      result['status'] = 0
    except Exception, e:
      LOG.exception(e)
      result['message'] = str(e)

  return HttpResponse(json.dumps(result), mimetype="application/json")
