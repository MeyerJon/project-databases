import os

from flask import Blueprint, jsonify, request, render_template, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import connection, data_loader, ALLOWED_EXTENSIONS, UPLOAD_FOLDER

api = Blueprint('api', __name__)


@api.route('/api/datasets/<int:dataset_id>/tables/<string:table_name>', methods=['GET'])
def get_table(dataset_id, table_name):
    start = request.args.get('start')
    length = request.args.get('length')
    ordering = (data_loader.get_column_names(dataset_id, table_name)[int(request.args.get('order[0][column]'))][0],
                request.args.get('order[0][dir]'))
    table = data_loader.get_table(dataset_id, table_name, offset=start, limit=length, ordering=ordering)
    _table = data_loader.get_table(dataset_id, table_name)  # TODO: This shit is dirty
    return jsonify(draw=int(request.args.get('draw')),
                   recordsTotal=len(_table.rows),
                   recordsFiltered=len(_table.rows),
                   data=table.rows)
