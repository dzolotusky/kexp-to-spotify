"""scrape old playlists from the KEXP API"""

import gzip
import requests
import json
import datetime
import time
import argparse

import spotipy
import spotipy.util as sputil

parser = argparse.ArgumentParser(description='Scrape some playlists.')
parser.add_argument('--start', type=str, help='earliest scrape date', default='')
parser.add_argument('--end', type=str, help='latest scrape date', default='')
parser.add_argument('--output_dir', type=str, default='output')

#21 is UTC for 2 PM in Seattle now (it'll be 22 later when Seattle is 8 behind and not 7)
PLAY_URL = 'https://legacy-api.kexp.org/play/?limit=200&end_time={}&ordering=-airdate&channel=1'
SHOW_URL = 'https://legacy-api.kexp.org/show/?showid='

def make_url(time) -> str:
    """create the URL to get all the plays for a single date"""
    return PLAY_URL.format(time)

def plays_for_date(time):
    """fetch all the plays for a single date"""
    url = make_url(time)
    response = requests.get(url)
    return response.json()['results']

def scrape_date(time, output_dir: str):
    plays = plays_for_date(time)
    # `plays` has a lot of repeated info, so we gzip the output files, which
    # gets them about 10x smaller. this probably isn't entirely necessary, but
    # I was running this on an ec2 instance without a lot of disk space.
    #with gzip.open('{}/{}.txt.gz'.format(output_dir, date.isoformat()), 'w') as f:
    #    for play in plays:
    #        f.write(bytes(json.dumps(play) + "\n", 'utf-8'))
    return plays

def no_john_or_cheryl(cur_show):
    no_john = True;
    show_response = requests.get(SHOW_URL + str(cur_show))
    shows = show_response.json()['results']
    if (len(shows) < 1):
        print("Play with less than 1 show")
        return False
    if (len(shows) > 1):
        print("Play with multiple shows")
        return False

    cur_show_name = shows[0]["program"]["name"]

    hosts = shows[0]['hosts']
    print ("show = " + shows[0]["program"]["name"])

    if cur_show_name == "Street Sounds":
        return False

    for host in hosts:
        print("host = " + host['name'])
        is_john = host['name'] == "John Richards" or host['name'] == "Cheryl Waters"
        no_john = no_john and not is_john

    return no_john

if __name__ == "__main__":
    token = sputil.prompt_for_user_token("dzolotusky", client_id='1310a11ef19c4ae29de1a51bddbba54d', client_secret='fee84ea8154a4e0fbc050a29aa55a46c', redirect_uri='http://www.kexp.org', scope='playlist-modify-public')
    sp = spotipy.Spotify(auth=token)

    args = parser.parse_args()

    plays = []

    month_string = '2018-03-'

    playlists = {}

    visited_plays = []

    for i in range(10, 18):
        date = month_string + str(i)
        print("reading data for {}".format(date))
        plays = scrape_date(date + "T" + "23:15:00" + "Z", args.output_dir)

        cur_show = 0
        cur_show_name = None
        no_john = True
        last_is_not_john = False

        is_monday = datetime.datetime.strptime(plays[-1]['airdate'], "%Y-%m-%dT%H:%M:%SZ").weekday()

        while (plays and (is_monday or not last_is_not_john)):
            last_play = plays[-1]
            is_monday = 0 == datetime.datetime.strptime(last_play['airdate'], "%Y-%m-%dT%H:%M:%SZ").weekday()
            last_is_not_john = no_john_or_cheryl(last_play['showid'])
            if (not last_is_not_john) or is_monday:
                plays.extend(scrape_date(last_play['airdate'], args.output_dir))
            else:
                print("verified that last track isn't John's or Cheryl's")

        prev_url = None
        for play in plays:
            if (play['playid'] in visited_plays):
                print ("skipping play number:" + str(play['playid']))
                continue

            visited_plays.append(play['playid'])
            if (play['showid'] != cur_show):
                prev_show = cur_show
                cur_show = play['showid']
                no_john = no_john_or_cheryl(cur_show)

                if no_john:
                    print("Show without John or Cheryl: " + str(cur_show))
                else:
                    show_response = requests.get(SHOW_URL + str(cur_show))
                    shows = show_response.json()['results']
                    cur_show_name = shows[0]["program"]["name"] + ' ' + date
                    if not cur_show_name in playlists:
                        playlists[cur_show_name] = []
                    hosts = shows[0]['hosts']
                    print("Show with " + hosts[0]['name'] + " " + str(cur_show))

                if prev_show == 0:
                    assert(no_john)
                    print ("verified that first track isn't John's or Cheryl's")

            if (not no_john and play['artist'] and play['track']):
                query_string = 'artist:' + play['artist']['name'] + ' track:' + play['track']['name']
                results = sp.search(q=query_string, limit=1)
                if len(results['tracks']['items']) > 0:
                    track = results['tracks']['items'][0]
                    if prev_url == track['uri']:
                        print ("just saw " + track['name'] + ' ' + track['uri'])
                    else:
                        print (' ', track['name'] + ' ' + track['uri'])
                        playlists[cur_show_name].append(track['uri'])
                        prev_url = track['uri']
                else:
                    print('FAILED TO FIND TRACK: ' + query_string)

        assert (no_john)
        print("verified that last track isn't John's or Cheryl's")

    for kexp_playlist in playlists:
        if (len(playlists[kexp_playlist]) > 0):
            playlist = sp.user_playlist_create('dzolotusky', 'KEXP - ' + kexp_playlist, True)
            playlists[kexp_playlist].reverse()
            sp.user_playlist_add_tracks(playlist_id=playlist['id'], user='dzolotusky', tracks=playlists[kexp_playlist])
            print ('Created ' + playlist['id'] + 'with ' + str(len(playlists[kexp_playlist])) + ' tracks')
            print("Found " + str(len(playlists[kexp_playlist])) + " tracks for " + kexp_playlist)
        else:
            print('Did not create playlist, no tracks found to add')