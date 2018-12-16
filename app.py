from flask import Flask, jsonify, request, Response
import os
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import requests
from requests.auth import HTTPBasicAuth
from functools import wraps
import git

app = Flask(__name__)
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    response = requests.get('https://api.github.com/teams/1825316/members', auth=HTTPBasicAuth(username, password))

    if response.status_code != 200:
        return False

    for user in response.json():
        if str(user['login']) == username:
            os.environ["GIT_USERNAME"] = username
            os.environ["GIT_PASSWORD"] = password
            return True

    return False


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.route('/sign_in', methods=['GET'])
@requires_auth
def sign_in():
    reset_creds()
    return jsonify([])


@app.route('/events', methods=['GET'])
@requires_auth
def get_events():
    reset_creds()
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flags = tools.argparser.parse_args(['--noauth_local_webserver'])
        flow = client.flow_from_clientsecrets(os.environ['GOOGLE_APPLICATION_CREDENTIALS'], SCOPES)
        creds = tools.run_flow(flow, store, flags)
    service = build('calendar', 'v3', http=creds.authorize(Http()))

    # Call the Calendar API
    events_result = service.events().list(calendarId='q3n3pce86072n9knt3pt65fhio@group.calendar.google.com',
                                          timeMin='2017-01-01T10:00:00Z',
                                          singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])
    return_events = []
    return_keys = ['start', 'summary', 'description', 'location']
    for event in events:
        return_events.append({key: event[key] for key in return_keys if key in event})

    return jsonify(return_events)


@app.route('/members', methods=['GET'])
@requires_auth
def get_members():
    reset_creds()
    admin_list_url = "https://join.uqcs.org.au/admin/list"
    options = Options()
    options.add_argument("--headless")
    options.add_argument('--no-sandbox')  # required when running as root user. otherwise you would get no sandbox
    driver = webdriver.Chrome(chrome_options=options)
    driver.implicitly_wait(30)
    driver.get(admin_list_url)

    while driver.current_url != "https://join.uqcs.org.au/admin/list":
        username = driver.find_element_by_name('username')
        username.send_keys(os.environ['UQCS_USER'])

        password = driver.find_element_by_name('password')
        password.send_keys(os.environ['UQCS_PASS'])

        submit_button = driver.find_element_by_name('submit')
        submit_button.click()

        driver.implicitly_wait(30)
        driver.get(admin_list_url)

    driver.implicitly_wait(30)

    members = []

    for row in driver.find_elements_by_tag_name('tr'):
        cells = row.find_elements_by_tag_name('td')
        members.append({'first_name': cells[0].text,
                        'last_name': cells[1].text,
                        'email': cells[2].text,
                        'paid': False if cells[3].text == 'None' else True})
    return jsonify(members[1:])  # cut off the titles of the table


@app.route('/docs', methods=['GET', 'POST'])
@requires_auth
def get_docs():
    # update the repo
    repo = git.Repo('../committee')
    repo.remotes.origin.pull()

    if request.method == 'POST':
        data = request.get_json(force=True)
        if 'file_name' in data and 'file_data' in data and 'commit_message' in data:
            for root, dirs, files in os.walk('../committee'):
                for file in files:
                    if str(file) == data['file_name']:
                        path = os.path.join(root, file)
                        open(path, "w").close()
                        f = open(path, "w")
                        f.write(str(data['file_data']))
                        f.close()
                        repo.git.add(os.path.abspath(path))

                        user_data = requests.get('https://api.github.com/users/' + os.environ['GIT_USERNAME'],
                                                 auth=HTTPBasicAuth(os.environ['GIT_USERNAME'],
                                                                    os.environ['GIT_PASSWORD']))

                        author = git.Actor(os.environ['GIT_USERNAME'], user_data.json()['email'])
                        repo.index.commit(data['commit_message'], author=author, committer=author)
                        repo.remotes.origin.push()
                        reset_creds()
                        return Response()

        else:
            reset_creds()
            return Response(400)

    else:
        # else request is get
        directory_dict = {}
        read_files("../committee", directory_dict)
        reset_creds()
        return jsonify(directory_dict)


def get_immediate_subdirectories(a_dir):
    return [name for name in os.listdir(a_dir)]


def read_files(path, json):
    directory_name = path.split('/')[-1]
    if directory_name not in json or json[directory_name] is None:
        json[directory_name] = {}

    for filename in get_immediate_subdirectories(path):
        if os.path.isfile(path + '/' + filename) and filename[-3:] == '.md':
            with open(path + "/" + filename, 'r') as my_file:
                data = my_file.read()
                json[directory_name][filename] = data
                continue

        if os.path.isdir(path + '/' + filename):
            if filename == ".git":
                continue
            json[directory_name][filename] = {}
            read_files(path + '/' + filename, json[directory_name])


def reset_creds():
    os.environ['GIT_USERNAME'] = ''
    os.environ['GIT_PASSWORD'] = ''


if __name__ == '__main__':
    app.run()
