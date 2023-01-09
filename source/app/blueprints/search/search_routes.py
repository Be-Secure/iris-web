#!/usr/bin/env python3
#
#  IRIS Source Code
#  Copyright (C) 2021 - Airbus CyberSecurity (SAS)
#  ir@cyberactionlab.net
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# IMPORTS ------------------------------------------------
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from flask_login import current_user
from sqlalchemy import and_
from sqlalchemy import or_

from app.forms import SearchForm
from app.iris_engine.access_control.utils import ac_flag_match_mask
from app.iris_engine.access_control.utils import ac_get_fast_user_cases_access
from app.iris_engine.search.search import SearchParser
from app.iris_engine.search.search_mapping import target_entities
from app.iris_engine.utils.tracker import track_activity
from app.models import Comments
from app.models.authorization import Permissions
from app.models.authorization import UserCaseAccess
from app.models.cases import Cases
from app.models.models import Client
from app.models.models import Ioc
from app.models.models import IocLink
from app.models.models import IocType
from app.models.models import Notes
from app.models.models import Tlp
from app.util import ac_api_requires
from app.util import ac_requires
from app.util import response_error
from app.util import response_success

search_blueprint = Blueprint('search',
                             __name__,
                             template_folder='templates')


# CONTENT ------------------------------------------------
@search_blueprint.route('/search/query', methods=['POST'])
@ac_api_requires(Permissions.server_administrator)
def search_query(caseid: int):
    jsdata = request.get_json()
    if jsdata is None:
        return response_success({'results': []})

    query = jsdata.get('query', '')
    if query == '':
        return response_success({'results': []})

    sp = SearchParser()
    sp.parse(query)

    return response_success({'results': []})

# CONTENT ------------------------------------------------

@search_blueprint.route('/search/target-entities', methods=['GET'])
@ac_api_requires(Permissions.standard_user)
def search_get_target_entities(caseid: int):
    return response_success(data=target_entities)

@search_blueprint.route('/search', methods=['POST'])
@ac_api_requires(Permissions.standard_user)
def search_file_post(caseid: int):

    jsdata = request.get_json()
    search_value = jsdata.get('search_value')
    search_type = jsdata.get('search_type')
    files = []
    search_condition = and_()

    track_activity("started a global search for {} on {}".format(search_value, search_type))

    user_search_limitations = ac_get_fast_user_cases_access(current_user.id)
    if user_search_limitations:
        search_condition = and_(Cases.case_id.in_(user_search_limitations))

    if search_type == 'query':

        sp = SearchParser()
        if sp.parse(search_value):
            results = [r._asdict() for r in sp.results]

            data = {'results': results,
                    'logs': sp.logs,
                    'columns': sp.entities,
                    'has_warnings': sp.has_warnings}

            return response_success(data=data)

        else:
            return response_error(msg='Search failed', data={'logs': sp.logs})

    if search_type == "ioc":
        res = Ioc.query.with_entities(
                            Ioc.ioc_value.label('ioc_name'),
                            Ioc.ioc_description.label('ioc_description'),
                            Ioc.ioc_misp,
                            IocType.type_name,
                            Tlp.tlp_name,
                            Tlp.tlp_bscolor,
                            Cases.name.label('case_name'),
                            Cases.case_id,
                            Client.name.label('customer_name')
                    ).filter(
                        and_(
                            Ioc.ioc_value.like(search_value),
                            IocLink.ioc_id == Ioc.ioc_id,
                            IocLink.case_id == Cases.case_id,
                            Client.client_id == Cases.client_id,
                            Ioc.ioc_tlp_id == Tlp.tlp_id,
                            search_condition
                        )
                    ).join(Ioc.ioc_type).all()

        files = [row._asdict() for row in res]

    if search_type == 'cases':
        res = Cases.query.with_entities(
                            Cases.name.label('case_name'),
                            Cases.case_id,
                            Client.name.label('customer_name')
                    ).filter(
                        and_(
                            or_(
                                Cases.name.like(search_value),
                                Cases.case_id.like(search_value),
                                Cases.description.like(search_value),
                                Cases.client.name.like(search_value)
                            ),
                            Client.client_id == Cases.client_id,
                            search_condition
                        )
                    ).all()

        files = [row._asdict() for row in res]

    if search_type == "notes":

        ns = []
        if search_value:
            search_value = "%{}%".format(search_value)
            ns = Notes.query.filter(
                Notes.note_content.like(search_value),
                Cases.client_id == Client.client_id,
                search_condition
            ).with_entities(
                Notes.note_id,
                Notes.note_title,
                Cases.name.label('case_name'),
                Client.name.label('client_name'),
                Cases.case_id
            ).join(
                Notes.case
            ).order_by(
                Client.name
            ).all()

            ns = [row._asdict() for row in ns]

        files = ns

    if search_type == "comments":
        search_value = "%{}%".format(search_value)
        comments = Comments.query.filter(
            Comments.comment_text.like(search_value),
            Cases.client_id == Client.client_id,
            search_condition
        ).with_entities(
            Comments.comment_id,
            Comments.comment_text,
            Cases.name.label('case_name'),
            Client.name.label('customer_name'),
            Cases.case_id
        ).join(
            Comments.case,
            Cases.client
        ).order_by(
            Client.name
        ).all()

        files = [row._asdict() for row in comments]

    return response_success("Results fetched", files)


@search_blueprint.route('/search', methods=['GET'])
@ac_requires(Permissions.standard_user)
def search_file_get(caseid, url_redir):
    if url_redir:
        return redirect(url_for('search.search_file_get', cid=caseid))

    form = SearchForm(request.form)
    return render_template('search.html', form=form)

