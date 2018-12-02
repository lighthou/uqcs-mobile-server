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

app = Flask(__name__)
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    for line in open(os.getcwd() + "/accountfile.txt", "r").readlines():  # Read the lines
        login_info = line.split()  # Split on the space, and store the results in a list of two strings
        if username == login_info[0] and password == login_info[1]:
            return True
    return False


def register(username, password):
    with open(os.getcwd() + '/accountfile.txt', "a") as creds_file:
        creds_file.write(username)
        creds_file.write(" ")
        creds_file.write(password)
        creds_file.write("\n")
        creds_file.close()


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


@app.route('/signin', methods=['POST'])
def validate_auth():
    username = request.form['username']
    password = request.form['password']

    response = requests.get('https://api.github.com/teams/1825316/members', auth=HTTPBasicAuth(username, password))

    if response.status_code != 200:
        return Response('', 401)

    for user in response.json():
        if str(user['login']) == username:
            register(username, password)
            return Response('', 200)

    return Response('', 401)


@app.route('/events', methods=['GET'])
@requires_auth
def get_events():
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


if __name__ == '__main__':
    app.run()
