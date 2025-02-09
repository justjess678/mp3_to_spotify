#!/usr/bin/env python

import base64
import os

import mutagen
import requests
from tqdm import tqdm
from hashlib import sha1
from random import random

import re
import json
import webbrowser
import click

CLIENT_SECRET = '1472c5382d674be6ae04a35e83464b35'
CLIENT_ID = 'be3478ead1a24f51b2245cd13411a77f'
REDIRECT_URI = 'http://localhost:8080/callback'


def clean_song(name):
	return (
    name.lower()
    .replace("clip officiel", "")
    .replace("[", "")
    .replace("]", "")
    .replace("(", "")
    .replace(")", "")
    .replace('"', "")
    .replace(" - ", " ")
    .replace("_", "")
    .replace(" ft. ", " ")
    .replace(" feat. ", " ")
    .replace(",", "")
    .replace(" x ", " ")
    .replace("lyrics", "")
    .replace("video", " ")
    .replace("audio only", "")
    .replace("radio edit", "")
    .replace("audio", "")
    .replace("hq", "")
    .replace("hd", "")
)

def read_songs(path):
	for root, dirs, files in os.walk(path):
		for name in files:
			if name.split('.')[-1] != 'mp3':
				continue

			track_path = os.path.join(root, name)
			f = mutagen.File(track_path)

			if not f['TPE1'].text[0] or not f['TIT2'].text[0]:
				query = clean_song(name.replace('.mp3', ''))
			else:
				query = "%s %s" % (f['TPE1'].text[0], f['TIT2'].text[0])

			yield re.sub(r'(.*)(\(.+\))(.*)', r'\1 \3', query)


def get_spotify_id(token, name):
	r1 = requests.get(url="https://api.spotify.com/v1/search?q=%s&type=track" % name,
					  headers={
						  'Authorization': 'Bearer %s' % token}
					  )

	results = r1.json()
	if r1.status_code != 200:
		print('ERROR GETTING SPOTIFY ID')
		return
	if len(results['tracks']['items']) == 0:
		return
	return results['tracks']['items'][0]['id']


def get_spotify_ids(token, path):
	for track in tqdm(list(read_songs(path))):
		id = get_spotify_id(token, track)
		if id is not None:
			yield id, None
		else:
			yield None, track
			# print('NOT FOUND', track)


@click.command()
@click.option('-d', '--directory', help='Directory in which to search for mp3 titles')
def process(directory):
	click.echo("------------------------")
	click.echo("| 🎵 MP3 TO SPOTIFY 🎵 |")
	click.echo("------------------------")
	if directory:
		path = directory
	else:
		path = click.prompt('Enter a path to directory to search in')

	state = sha1(str(random()).encode('utf-8')).hexdigest()

	# 1. Authorize spotify access
	authorize_url = "https://accounts.spotify.com/authorize?client_id=%s&response_type=code&redirect_uri=%s&scope=user-library-read user-library-modify&state=%s" % (
		CLIENT_ID, REDIRECT_URI, state)

	click.echo('Visit this URL in your browser: ' + authorize_url)
	webbrowser.open(authorize_url)
	click.echo("")
	url_with_code = click.prompt("Copy URL from your browser's address bar")
	click.echo("")

	# Retrieve code parameter
	code = re.search('code=([^&]*)', url_with_code).group(1)

	# Retrieve state parameter
	returned_state = re.search('state=([^&]*)', url_with_code).group(1)

	assert returned_state == state, 'State parameters do no match! Bailing out.'

	# 2. Getting the token access
	auth = "%s:%s" % (CLIENT_ID, CLIENT_SECRET)
	r = requests.post(url='https://accounts.spotify.com/api/token',
					  params={"grant_type": "authorization_code", "code": code,
							  "redirect_uri": REDIRECT_URI},
					  headers={'Content-Type': 'application/x-www-form-urlencoded',
							   'Authorization': 'Basic ' + base64.b64encode(
								   auth.encode()).decode()})

	if r.status_code != 200:
		raise Exception('ERROR GETTING TOKEN')

	token = r.json()['access_token']

	# 3. Getting the tracks id from spotify
	click.echo("➡️  Retrieving the track's id from Spotify")
	all_tracks = list(get_spotify_ids(token, path))
	tracks_to_add = list(filter(lambda x: x is not None, [x[0] for x in all_tracks]))
	not_found_tracks = list(filter(lambda x: x is not None, [x[1] for x in all_tracks]))

	click.echo("")

	if len(tracks_to_add) == 0:
		raise Exception('no tracks to add')

	# 4. Adding song to library by chunk of 50 (API limit)
	click.echo("➡️  Adding found tracks to Spotify library")
	for part in tqdm([tracks_to_add[x:x + 50] for x in range(0, len(tracks_to_add), 50)]):
		r = requests.put(url='https://api.spotify.com/v1/me/tracks',
						 data=json.dumps({'ids': part}),
						 headers={
							 'Content-Type': 'application/json',
							 'Authorization': 'Bearer %s' % token})

		if r.status_code != 200:
			raise Exception('Error adding tracks to library')

	click.echo()
	click.echo("✅ %d tracks successfully added to your Spotify account 👏" % (len(tracks_to_add)))

	click.echo()

	if len(not_found_tracks) > 0:
		click.echo("❌ %d/%d tracks not found on Spotify, try adding manually : %a" % (len(not_found_tracks), len(all_tracks), not_found_tracks))


if __name__ == '__main__':
	process()
