import datetime
import typing

import flask
import flask_restful

from scoutingbackend.cachingsession import session
from scoutingbackend.database import db


class BlueAlliance(object):
    def __init__(self, api_key: str) -> None:
        session.headers['X-TBA-Auth-Key'] = api_key
        
        self.bp = flask.Blueprint('ba', __name__, url_prefix='/bluealliance')
        self.rest = flask_restful.Api(self.bp)
        self.rest.add_resource(self.BAIndex, '/')
        self.rest.add_resource(self.BASeason, '/<int:season>')
        self.rest.add_resource(self.BAEvent, '/<int:season>/<string:event>')
        self.rest.add_resource(self.BAMatch, '/<int:season>/<string:event>/<string:match>')
    
    def register(self, app: typing.Union[flask.Flask, flask.Blueprint]):
        app.register_blueprint(self.bp)
    
    @staticmethod
    def is_valid_event(event: dict, ignore_date=False):
        start_date = datetime.datetime.strptime(event['start_date'], r"%Y-%m-%d",).date()
        end_date = datetime.datetime.strptime(event['end_date'], r"%Y-%m-%d").date()
        today = datetime.date.today()
        return ("TBA_STATE" not in flask.current_app.config or event['state_prov'] == flask.current_app.config['TBA_STATE']) and (ignore_date or start_date <= today <= end_date)
    
    class BAIndex(flask_restful.Resource):
        def get(self):
            resp = session.get("https://www.thebluealliance.com/api/v3/status", cache_control=flask.request.cache_control)
            if not resp.ok:
                return flask_restful.abort(resp.status_code)
            j = resp.json()
            return {"max_season": j['max_season'], "current_season": j['current_season']}
            
    class BASeason(flask_restful.Resource):
        def get(self, season: int):
            ignore_date = flask.request.args.get('ignoreDate', "false").lower()=="true"
            resp = session.get(f"https://www.thebluealliance.com/api/v3/events/{season}/simple", cache_control=flask.request.cache_control)
            if not resp.ok:
                return flask_restful.abort(resp.status_code)
            j = resp.json()
            return {e['event_code']: e['name'] for e in j if BlueAlliance.is_valid_event(e, ignore_date)}
    
    class BAEvent(flask_restful.Resource):
        def get(self, season: int, event: str):
            resp = session.get(f"https://www.thebluealliance.com/api/v3/event/{season}{event}/matches/simple", cache_control=flask.request.cache_control)
            if not resp.ok:
                return flask_restful.abort(resp.status_code)
            j = resp.json()
            return {e['key'].split("_")[-1]: e['key'] for e in j}
        
    class BAMatch(flask_restful.Resource):
        def get(self, season: int, event: str, match: str):
            if match == "*":
                resp = session.get(f"https://www.thebluealliance.com/api/v3/event/{season}{event}/teams/keys", cache_control=flask.request.cache_control)
                if not resp.ok:
                    return flask_restful.abort(resp.status_code)
                
                if flask.request.args.get("onlyUnfilled", "false") == "true":
                    try:
                        scoutedlist = [t['teamNumber'] for t in db.cursor().execute(f"SELECT (teamNumber) FROM frc{season}{event}_pit").fetchall()]
                    except:
                        scoutedlist = []
                    full_list = [int(team_code[3:]) for team_code in resp.json()]
                    return list(set(full_list).difference(scoutedlist))
                else:
                    return {team_code[3:]: "*" for team_code in resp.json()}
            resp = session.get(f"https://www.thebluealliance.com/api/v3/match/{season}{event}_{match}/simple", cache_control=flask.request.cache_control)
            if not resp.ok:
                return flask_restful.abort(resp.status_code)
            j = resp.json()
            if 'Error' in j:
                return flask_restful.abort(401, description=j['Error'])
            o = {}
            for alliance, allianceData in j['alliances'].items():
                for teamCode in allianceData['team_keys']:
                    o[teamCode[3:]] = alliance
            return o