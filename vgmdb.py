"""Adds VGMdb search support to Beets
"""
from beets.autotag.hooks import AlbumInfo, TrackInfo, Distance
from beets.plugins import BeetsPlugin
import sys
import logging
import requests
import re

log = logging.getLogger('beets')

class VGMdbPlugin(BeetsPlugin):

    def __init__(self):
        super(VGMdbPlugin, self).__init__()
        self.config.add({
            'source_weight': 1.0,
            'lang-priority': 'en, ja-latn'
        })
        log.debug('Querying VGMdb')
        self.source_weight = self.config['source_weight'].as_number()
        self.lang = self.config['lang-priority'].get().split(",")

    def album_distance(self, items, album_info, mapping):
        """Returns the album distance.
        """
        dist = Distance()
        if album_info.data_source == 'VGMdb':
            dist.add('source', self.source_weight)
        return dist

    def candidates(self, items, artist, album, va_likely):
        """Returns a list of AlbumInfo objects for VGMdb search results
        matching an album and artist (if not various).
        """
        if va_likely:
            query = album
        else:
            query = '%s %s' % (artist, album)
        try:
            return self.get_albums(query, va_likely)
        except:
            log.debug('VGMdb Search Error: (query: %s)' % query)
            return []

    def album_for_id(self, album_id):
        """Fetches an album by its VGMdb ID and returns an AlbumInfo object
        or None if the album is not found.
        """
        log.debug('Querying VGMdb for release %s' % str(album_id))

	# Get from VGMdb
        r = requests.get('http://vgmdb.info/album/%s?format=json' % str(album_id))

	# Decode Response's content
	try:
	    item = r.json()
	except:
	    log.debug('VGMdb JSON Decode Error: (id: %s)' % album_id)
	    return None

        return self.get_album_info(item, False)

    def get_albums(self, query, va_likely):
        """Returns a list of AlbumInfo objects for a VGMdb search query.
        """
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Use `re.UNICODE` flag to avoid stripping non-english
        # word characters.
        query = re.sub(r'(?u)\W+', ' ', query)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r'(?i)\b(CD|disc)\s*\d+', '', query)

	# Query VGMdb
	r = requests.get('http://vgmdb.info/search/albums/%s?format=json' % query)
	albums = []

	# Decode Response's content
 	try:
	    items = r.json()
	except:
	    log.debug('VGMdb JSON Decode Error: (query: %s)' % query)
	    return albums

	# Break up and get search results
        for item in items["results"]["albums"]:
	    album_id = str(self.decod(item["link"][6:]))
            albums.append(self.album_for_id(album_id))
            if len(albums) >= 5:
                break
        log.debug('get_albums Querying VGMdb for release %s' % str(query))
        return albums

    def decod(self, val, codec='utf8'):
        """Ensure that all string are coded to Unicode.
        """
        if isinstance(val, basestring):
            return val.decode(codec, 'ignore')

    def get_album_info(self, item, va_likely):
        """Convert json data into a format beets can read
        """

	# If a preferred lang is available use that instead
	album_name = item["name"]
	for lang in self.lang:
            if item["names"].has_key(lang):
	        album_name = item["names"][lang]

        album_id = item["link"][6:]
        country = "JP"
	catalognum = item["catalog"]

	# Get Artist information
        if item.has_key("performers") and len(item["performers"]) > 0:
            artist_type = "performers"
        else:
            artist_type = "composers"

	artists = []
	for artist in item[artist_type]:
	    if artist["names"].has_key(self.lang[0]):
	        artists.append(artist["names"][self.lang[0]])
            else:
                artists.append(artist["names"]["ja"])

        artist = artists[0]
        if item[artist_type][0].has_key("link"):
            artist_id = item[artist_type][0]["link"][7:]
        else:
            artist_id = None

	# Get Track metadata
        Tracks = []
	total_index = 0
        for disc_index, disc in enumerate(item["discs"]):
            for track_index, track in enumerate(disc["tracks"]):
                total_index += 1

                if track["names"].has_key("English"):
                    title = track["names"]["English"]
                elif track["names"].has_key("Romaji"):
                    title = track["names"]["Romaji"]
                else:
                    title = track["names"].values()[0]

                index = total_index

                if track["track_length"] == "Unknown":
                    length = 0
                else:
                    length = track["track_length"].split(":")
                    length = (float(length[0]) * 60) + float(length[1])

                media = item["media_format"]
		medium = disc_index
                medium_index = track_index
                new_track = TrackInfo(
                    title,
                    int(index),
		    length=float(length),
                    index=int(index),
                    medium=int(medium),
                    medium_index=int(medium_index),
                    medium_total=item["discs"].count
                    )
                Tracks.append(new_track)

	# Format Album release date
	release_date = item["release_date"].split("-")
        year  = release_date[0]
        month = release_date[1]
        day   = release_date[2]

        if item["publisher"]["names"].has_key(self.lang[0]):
            label = item["publisher"]["names"][self.lang[0]]
        else:
            label = item["publisher"]["names"]["ja"]

        mediums = len(item["discs"])
        media = item["media_format"]

        data_url = item["vgmdb_link"]

        return AlbumInfo(album_name,
                        self.decod(album_id),
                        artist,
                        self.decod(artist_id),
                        Tracks,
                        asin=None,
                        albumtype=None,
                        va=False,
                        year=int(year),
                        month=int(month),
                        day=int(day),
                        label=label,
                        mediums=int(mediums),
                        media=self.decod(media),
                        data_source=self.decod('VGMdb'),
                        data_url=self.decod(data_url),
                        country=self.decod(country),
                        catalognum=self.decod(catalognum)
                     )
