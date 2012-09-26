## Licensed to Cloudera, Inc. under one
## or more contributor license agreements.  See the NOTICE file
## distributed with this work for additional information
## regarding copyright ownership.  Cloudera, Inc. licenses this file
## to you under the Apache License, Version 2.0 (the
## "License"); you may not use this file except in compliance
## with the License.  You may obtain a copy of the License at
##
##     http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.
<%!
    from django.utils.translation import ugettext as _
%>

<%def name="render()">
    <div class="well" style="padding-top: 10px; padding-bottom: 0">
        <p class="pull-right">
            %if hasattr(caller, "creation"):
                ${caller.creation()}
            %endif
        </p>
        <p>
            %if hasattr(caller, "search"):
                ${caller.search()}
            %else:
                <strong>${_('Filter')}:</strong> <input id="filterInput" type="text" class="input-xlarge search-query" placeholder="${_('Search...')}">
            %endif
            %if hasattr(caller, "actions"):
                &nbsp;&nbsp;&nbsp;&nbsp;
                ${caller.actions()}
            %endif
        </p>
    </div>
</%def>