#!/usr/bin/env python3

import requests
import json
import xml.dom.minidom
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# Complete channel lineup from HDHomeRun - exact match to actual lineup
CHANNELS = {
    # Exact match to HDHomeRun lineup from http://192.168.50.130/lineup.json
    2.1: {'name': 'WPBT-HD', 'network': 'PBS'},
    2.2: {'name': 'Create', 'network': 'Create'},
    2.3: {'name': 'WPBTHC', 'network': 'PBS'},
    2.4: {'name': 'Kids', 'network': 'PBS Kids'},
    4.1: {'name': 'WFOR-TV', 'network': 'CBS'},
    4.2: {'name': 'WFORTV2', 'network': 'Start TV'},
    4.3: {'name': 'WFORTV3', 'network': 'Dabl'},
    4.4: {'name': 'WFORTV4', 'network': 'CBSN'},
    4.5: {'name': 'WFORTV5', 'network': 'Fave TV'},
    6.1: {'name': 'WTVJ', 'network': 'NBC'},
    6.2: {'name': 'COZI TV', 'network': 'Cozi TV'},
    6.3: {'name': 'AMCRIME', 'network': 'True Crime'},
    6.4: {'name': 'Oxygen', 'network': 'Oxygen'},
    7.1: {'name': 'WSVN', 'network': 'FOX'},
    7.2: {'name': 'ABC', 'network': 'ABC'},
    7.3: {'name': 'The365', 'network': 'The 365'},
    7.4: {'name': 'DEFY', 'network': 'Defy TV'},
    13.1: {'name': 'WURH', 'network': 'Independent'},
    17.1: {'name': 'WLRN-HD', 'network': 'PBS'},
    18.1: {'name': 'ABC18.1', 'network': 'ABC'},
    23.1: {'name': 'WLTV-DT', 'network': 'Univision'},
    23.2: {'name': 'JUSTICE', 'network': 'Justice Network'},
    23.3: {'name': 'Nosey', 'network': 'Nosey'},
    23.4: {'name': 'MSGold', 'network': 'Movies! Gold'},
    23.6: {'name': 'ShopLC', 'network': 'Shop LC'},
    33.1: {'name': 'WBFS-TV', 'network': 'CW'},
    33.2: {'name': 'WBFSTV2', 'network': 'Antenna TV'},
    33.3: {'name': 'WBFSTV3', 'network': 'CourtTV'},
    33.4: {'name': 'WBFSTV4', 'network': 'Story Television'},
    33.5: {'name': 'WBFSTV5', 'network': 'True Crime Network'},
    33.6: {'name': 'WBFSTV6', 'network': 'Newsy'},
    33.7: {'name': 'WBFSTV7', 'network': 'Rewind TV'},
    39.1: {'name': 'WSFL-DT', 'network': 'CW'},
    39.2: {'name': 'CourtTV', 'network': 'CourtTV'},
    39.3: {'name': 'AntTV', 'network': 'Antenna TV'},
    39.4: {'name': 'IONPLUS', 'network': 'ION Plus'},
    39.5: {'name': 'QVC', 'network': 'QVC'},
    42.1: {'name': 'WXEL-HD', 'network': 'PBS'},
    45.1: {'name': 'TBN HD', 'network': 'TBN'},
    45.2: {'name': 'Merit', 'network': 'Merit Street'},
    45.3: {'name': 'Inspire', 'network': 'Inspire'},
    45.4: {'name': 'ONTV4U', 'network': 'ONTV4U'},
    45.5: {'name': 'POSITIV', 'network': 'Positiv'},
    51.1: {'name': 'WSCV', 'network': 'Telemundo'},
    51.2: {'name': 'EXITOS', 'network': 'Exitos'},
    51.4: {'name': 'WSCV-PB', 'network': 'NBC Universo'},
    63.1: {'name': 'WBEC-HD', 'network': 'Independent'},
    63.2: {'name': 'WBEC-SD', 'network': 'Independent'},
    67.1: {'name': 'ION', 'network': 'ION'},
    67.2: {'name': 'Mystery', 'network': 'ION Mystery'},
    67.3: {'name': 'DEFY', 'network': 'Defy TV'},
    67.4: {'name': 'DABL', 'network': 'Dabl'},
    67.5: {'name': 'BUSTED', 'network': 'TruTV'},
    67.6: {'name': 'GameSho', 'network': 'Game Show Network'},
    67.7: {'name': 'HSN2', 'network': 'HSN2'},
    67.8: {'name': 'HSN', 'network': 'HSN'},
    67.9: {'name': 'QVC', 'network': 'QVC'},
    69.1: {'name': 'WAMI-DT', 'network': 'MyNetworkTV'},
    69.2: {'name': 'Confess', 'network': 'Court TV'},
    69.3: {'name': 'getTV', 'network': 'getTV'},
    69.4: {'name': 'BT2', 'network': 'Bounce'},
    69.5: {'name': 'QUEST', 'network': 'Quest'}
}

def get_fallback_schedule(network):
    """Generate fallback programming schedule based on network type."""
    
    if network == 'CBS':
        schedule = [
            ('CBS This Morning', 180, 'News'),
            ('The Price is Right', 60, 'Game Show'),
            ('The Young and the Restless', 60, 'Drama'),
            ('The Bold and the Beautiful', 30, 'Drama'),
            ('The Talk', 60, 'Talk Show'),
            ('Let\'s Make a Deal', 30, 'Game Show'),
            ('CBS Evening News', 30, 'News'),
            ('Entertainment Tonight', 30, 'Entertainment'),
            ('NCIS', 60, 'Crime Drama'),
            ('FBI', 60, 'Crime Drama'),
            ('Late Night Programming', 240, 'Various')
        ]
    elif network == 'NBC':
        schedule = [
            ('Today Show', 240, 'News'),
            ('Days of Our Lives', 60, 'Drama'),
            ('NBC Nightly News', 30, 'News'),
            ('Access Hollywood', 30, 'Entertainment'),
            ('Chicago Fire', 60, 'Drama'),
            ('Chicago Med', 60, 'Drama'),
            ('Chicago P.D.', 60, 'Drama'),
            ('Late Night with Seth Meyers', 60, 'Talk Show'),
            ('Saturday Night Live', 90, 'Comedy'),
            ('Overnight Programming', 180, 'Various')
        ]
    elif network == 'ABC':
        schedule = [
            ('Good Morning America', 180, 'News'),
            ('General Hospital', 60, 'Drama'),
            ('The View', 60, 'Talk Show'),
            ('World News Tonight', 30, 'News'),
            ('Wheel of Fortune', 30, 'Game Show'),
            ('Jeopardy!', 30, 'Game Show'),
            ('Grey\'s Anatomy', 60, 'Medical Drama'),
            ('Station 19', 60, 'Drama'),
            ('Jimmy Kimmel Live!', 60, 'Talk Show'),
            ('Nightline', 30, 'News'),
            ('Overnight News', 240, 'News')
        ]
    elif network == 'FOX':
        schedule = [
            ('Good Day Miami', 300, 'Morning Show'),
            ('The People\'s Court', 60, 'Court Show'),
            ('Judge Judy', 30, 'Court Show'),
            ('FOX 7 News', 30, 'News'),
            ('The Simpsons', 30, 'Animation'),
            ('Family Guy', 30, 'Animation'),
            ('9-1-1', 60, 'Drama'),
            ('The Resident', 60, 'Medical Drama'),
            ('FOX 7 Late News', 35, 'News'),
            ('The Late Show', 240, 'Various')
        ]
    elif network == 'PBS':
        schedule = [
            ('PBS NewsHour', 60, 'News'),
            ('Masterpiece', 90, 'Drama'),
            ('Nature', 60, 'Documentary'),
            ('NOVA', 60, 'Documentary'),
            ('Antiques Roadshow', 60, 'Reality'),
            ('Frontline', 60, 'Documentary'),
            ('American Experience', 120, 'Documentary'),
            ('Independent Lens', 90, 'Documentary'),
            ('Charlie Rose', 60, 'Interview'),
            ('Overnight Programming', 180, 'Educational')
        ]
    elif network in ['CW', 'The CW']:
        schedule = [
            ('Morning Programming', 240, 'Various'),
            ('Judge Mathis', 60, 'Court Show'),
            ('Maury', 60, 'Talk Show'),
            ('Jerry Springer', 60, 'Talk Show'),
            ('Local News', 30, 'News'),
            ('Riverdale', 60, 'Teen Drama'),
            ('The Flash', 60, 'Superhero'),
            ('Supergirl', 60, 'Superhero'),
            ('Arrow', 60, 'Superhero'),
            ('Late Movies', 180, 'Movies')
        ]
    elif network == 'ION':
        schedule = [
            ('NCIS', 60, 'Crime Drama'),
            ('NCIS: New Orleans', 60, 'Crime Drama'),
            ('NCIS: Los Angeles', 60, 'Crime Drama'),
            ('Criminal Minds', 60, 'Crime Drama'),
            ('Chicago P.D.', 60, 'Crime Drama'),
            ('Chicago Fire', 60, 'Crime Drama'),
            ('Chicago Med', 60, 'Crime Drama'),
            ('Law & Order SVU', 60, 'Crime Drama'),
            ('Blue Bloods', 60, 'Crime Drama'),
            ('FBI', 60, 'Crime Drama')
        ]
    elif network == 'MyNetworkTV':
        schedule = [
            ('Divorce Court', 60, 'Court Show'),
            ('The Steve Wilkos Show', 60, 'Talk Show'),
            ('Maury', 60, 'Talk Show'),
            ('Jerry Springer', 60, 'Talk Show'),
            ('Local Programming', 120, 'Various'),
            ('Movies', 180, 'Movies'),
            ('Sitcom Reruns', 120, 'Comedy'),
            ('Late Night Movies', 180, 'Movies')
        ]
    elif network == 'MeTV':
        schedule = [
            ('The Andy Griffith Show', 60, 'Classic Comedy'),
            ('Leave it to Beaver', 30, 'Classic Comedy'),
            ('The Beverly Hillbillies', 30, 'Classic Comedy'),
            ('Gunsmoke', 60, 'Western'),
            ('Bonanza', 60, 'Western'),
            ('The Big Valley', 60, 'Western'),
            ('Perry Mason', 60, 'Mystery'),
            ('The Twilight Zone', 60, 'Sci-Fi'),
            ('Star Trek', 60, 'Sci-Fi'),
            ('The Honeymooners', 30, 'Classic Comedy')
        ]
    elif network == 'Heroes & Icons':
        schedule = [
            ('MacGyver', 60, 'Action'),
            ('The A-Team', 60, 'Action'),
            ('Knight Rider', 60, 'Action'),
            ('Magnum P.I.', 60, 'Action'),
            ('The Rockford Files', 60, 'Mystery'),
            ('Kojak', 60, 'Crime Drama'),
            ('The Streets of San Francisco', 60, 'Crime Drama'),
            ('Hill Street Blues', 60, 'Crime Drama'),
            ('Miami Vice', 60, 'Crime Drama'),
            ('Emergency!', 60, 'Action Drama')
        ]
    elif network == 'Antenna TV':
        schedule = [
            ('Three\'s Company', 30, 'Classic Comedy'),
            ('All in the Family', 30, 'Classic Comedy'),
            ('The Jeffersons', 30, 'Classic Comedy'),
            ('Good Times', 30, 'Classic Comedy'),
            ('What\'s Happening!!', 30, 'Classic Comedy'),
            ('The Partridge Family', 30, 'Classic Comedy'),
            ('That Girl', 30, 'Classic Comedy'),
            ('Bewitched', 30, 'Classic Comedy'),
            ('I Dream of Jeannie', 30, 'Classic Comedy'),
            ('The Monkees', 30, 'Classic Comedy')
        ]
    elif network == 'getTV':
        schedule = [
            ('Magnum P.I.', 60, 'Action'),
            ('The Rockford Files', 60, 'Mystery'),
            ('Kojak', 60, 'Crime Drama'),
            ('The Streets of San Francisco', 60, 'Crime Drama'),
            ('Quincy M.E.', 60, 'Crime Drama'),
            ('The Equalizer', 60, 'Action'),
            ('Sanford and Son', 30, 'Comedy'),
            ('Good Times', 30, 'Comedy'),
            ('What\'s Happening!!', 30, 'Comedy'),
            ('Movies', 180, 'Movies')
        ]
    elif network == 'Movies!':
        schedule = [
            ('Classic Movies', 120, 'Movies'),
            ('Action Movies', 120, 'Movies'),
            ('Drama Movies', 120, 'Movies'),
            ('Comedy Movies', 90, 'Movies'),
            ('Western Movies', 120, 'Movies'),
            ('Sci-Fi Movies', 120, 'Movies'),
            ('Horror Movies', 90, 'Movies'),
            ('Romance Movies', 120, 'Movies'),
            ('Mystery Movies', 120, 'Movies'),
            ('Late Night Movies', 180, 'Movies')
        ]
    elif network == 'THIS TV':
        schedule = [
            ('Classic TV Shows', 60, 'Classic TV'),
            ('Action Movies', 120, 'Movies'),
            ('Comedy Movies', 90, 'Movies'),
            ('Drama Movies', 120, 'Movies'),
            ('TV Movies', 120, 'Movies'),
            ('Miniseries', 120, 'Drama'),
            ('Classic Sitcoms', 60, 'Comedy'),
            ('Vintage Variety Shows', 60, 'Variety'),
            ('Late Night Features', 180, 'Movies')
        ]
    elif network == 'Cozi TV':
        schedule = [
            ('Little House on the Prairie', 60, 'Family Drama'),
            ('The Waltons', 60, 'Family Drama'),
            ('Highway to Heaven', 60, 'Family Drama'),
            ('Frasier', 30, 'Comedy'),
            ('Cheers', 30, 'Comedy'),
            ('Wings', 30, 'Comedy'),
            ('Murder, She Wrote', 60, 'Mystery'),
            ('Columbo', 120, 'Mystery'),
            ('McMillan & Wife', 90, 'Mystery'),
            ('Family Movies', 120, 'Movies')
        ]
    elif network in ['Bounce', 'Bounce TV']:
        schedule = [
            ('Family Matters', 30, 'Comedy'),
            ('The Hughleys', 30, 'Comedy'),
            ('One on One', 30, 'Comedy'),
            ('The Parkers', 30, 'Comedy'),
            ('Living Single', 30, 'Comedy'),
            ('Martin', 30, 'Comedy'),
            ('The Bernie Mac Show', 30, 'Comedy'),
            ('The Steve Harvey Show', 30, 'Comedy'),
            ('In the House', 30, 'Comedy'),
            ('Urban Movies', 120, 'Movies')
        ]
    elif network == 'Laff':
        schedule = [
            ('Home Improvement', 30, 'Comedy'),
            ('Roseanne', 30, 'Comedy'),
            ('Night Court', 30, 'Comedy'),
            ('Scrubs', 30, 'Comedy'),
            ('3rd Rock from the Sun', 30, 'Comedy'),
            ('That \'70s Show', 30, 'Comedy'),
            ('Spin City', 30, 'Comedy'),
            ('NewsRadio', 30, 'Comedy'),
            ('Just Shoot Me!', 30, 'Comedy'),
            ('Comedy Movies', 120, 'Movies')
        ]
    elif network in ['Grit', 'Grit TV']:
        schedule = [
            ('Western Movies', 120, 'Western'),
            ('Action Movies', 120, 'Action'),
            ('War Movies', 150, 'War'),
            ('Martial Arts Movies', 90, 'Action'),
            ('Tough Guy Movies', 120, 'Action'),
            ('Classic Westerns', 120, 'Western'),
            ('Adventure Movies', 120, 'Adventure'),
            ('Crime Movies', 120, 'Crime'),
            ('Thriller Movies', 120, 'Thriller')
        ]
    elif network in ['Defy TV', 'Defy']:
        schedule = [
            ('Stunt Shows', 60, 'Reality'),
            ('Extreme Sports', 60, 'Sports'),
            ('Adventure Shows', 60, 'Adventure'),
            ('Military Shows', 60, 'Military'),
            ('Survival Shows', 60, 'Reality'),
            ('Competition Shows', 60, 'Competition'),
            ('Action Series', 60, 'Action'),
            ('Adventure Movies', 120, 'Movies')
        ]
    elif network == 'TrueReal':
        schedule = [
            ('Crime Documentaries', 60, 'Documentary'),
            ('Investigation Shows', 60, 'Crime'),
            ('True Crime Series', 60, 'Crime'),
            ('Mystery Documentaries', 60, 'Mystery'),
            ('Forensic Shows', 60, 'Crime'),
            ('Cold Case Files', 60, 'Crime'),
            ('Detective Stories', 60, 'Crime'),
            ('Real Crime', 60, 'Crime')
        ]
    elif network in ['Court TV', 'CourtTV']:
        schedule = [
            ('Morning Court', 180, 'Court'),
            ('Live Trial Coverage', 240, 'Court'),
            ('Forensic Files', 30, 'Crime'),
            ('Cold Case Files', 60, 'Crime'),
            ('The First 48', 60, 'Crime'),
            ('Nightwatch', 60, 'Reality'),
            ('Body Cam', 30, 'Crime'),
            ('Prime Crime', 120, 'Crime')
        ]
    elif network == 'Court TV Mystery':
        schedule = [
            ('Perry Mason', 60, 'Mystery'),
            ('Matlock', 60, 'Mystery'),
            ('Murder, She Wrote', 60, 'Mystery'),
            ('Columbo', 120, 'Mystery'),
            ('McMillan & Wife', 90, 'Mystery'),
            ('McCloud', 90, 'Mystery'),
            ('Quincy M.E.', 60, 'Mystery'),
            ('Mystery Movies', 120, 'Mystery')
        ]
    elif network in ['Game Show Network', 'GSN']:
        schedule = [
            ('Family Feud', 30, 'Game Show'),
            ('The Price is Right', 60, 'Game Show'),
            ('Let\'s Make a Deal', 30, 'Game Show'),
            ('Deal or No Deal', 60, 'Game Show'),
            ('Wheel of Fortune', 30, 'Game Show'),
            ('Jeopardy!', 30, 'Game Show'),
            ('Password', 30, 'Game Show'),
            ('Match Game', 30, 'Game Show'),
            ('Card Sharks', 30, 'Game Show'),
            ('Press Your Luck', 30, 'Game Show')
        ]
    elif network == 'Buzzr':
        schedule = [
            ('Password', 30, 'Game Show'),
            ('Match Game', 30, 'Game Show'),
            ('Family Feud', 30, 'Game Show'),
            ('Card Sharks', 30, 'Game Show'),
            ('Press Your Luck', 30, 'Game Show'),
            ('Sale of the Century', 30, 'Game Show'),
            ('Super Password', 30, 'Game Show'),
            ('Blockbusters', 30, 'Game Show'),
            ('Classic Concentration', 30, 'Game Show'),
            ('Double Dare', 30, 'Game Show')
        ]
    elif network in ['Start TV', 'Start']:
        schedule = [
            ('MacGyver', 60, 'Action'),
            ('The Closer', 60, 'Crime Drama'),
            ('Major Crimes', 60, 'Crime Drama'),
            ('Cold Case', 60, 'Crime Drama'),
            ('Without a Trace', 60, 'Crime Drama'),
            ('The Good Wife', 60, 'Legal Drama'),
            ('Person of Interest', 60, 'Crime Drama'),
            ('Elementary', 60, 'Mystery'),
            ('Unforgotten', 90, 'Mystery'),
            ('Police Procedurals', 60, 'Crime Drama')
        ]
    elif network == 'Dabl':
        schedule = [
            ('Sister, Sister', 30, 'Comedy'),
            ('Moesha', 30, 'Comedy'),
            ('The Game', 30, 'Comedy'),
            ('Girlfriends', 30, 'Comedy'),
            ('Half & Half', 30, 'Comedy'),
            ('One on One', 30, 'Comedy'),
            ('The Parkers', 30, 'Comedy'),
            ('Living Single', 30, 'Comedy'),
            ('Martin', 30, 'Comedy'),
            ('Comedy Block', 120, 'Comedy')
        ]
    elif network in ['Charge!', 'Charge']:
        schedule = [
            ('The Equalizer', 60, 'Action'),
            ('Hunter', 60, 'Action'),
            ('T.J. Hooker', 60, 'Action'),
            ('Renegade', 60, 'Action'),
            ('Viper', 60, 'Action'),
            ('Soldier of Fortune', 60, 'Action'),
            ('Action Movies', 120, 'Movies'),
            ('Martial Arts Theater', 120, 'Movies'),
            ('Crime Movies', 120, 'Movies')
        ]
    elif network == 'Comet':
        schedule = [
            ('Stargate SG-1', 60, 'Sci-Fi'),
            ('Stargate Atlantis', 60, 'Sci-Fi'),
            ('Andromeda', 60, 'Sci-Fi'),
            ('Babylon 5', 60, 'Sci-Fi'),
            ('Buck Rogers', 60, 'Sci-Fi'),
            ('Battlestar Galactica', 60, 'Sci-Fi'),
            ('Sci-Fi Movies', 120, 'Sci-Fi'),
            ('Horror Movies', 120, 'Horror'),
            ('Fantasy Movies', 120, 'Fantasy')
        ]
    elif network in ['TBD', 'TBD TV']:
        schedule = [
            ('Very Local', 60, 'News'),
            ('Weather News', 30, 'Weather'),
            ('Local Interest', 60, 'Documentary'),
            ('Travel Shows', 60, 'Travel'),
            ('Food Shows', 60, 'Cooking'),
            ('Home & Garden', 60, 'Lifestyle'),
            ('Tech Reviews', 30, 'Technology'),
            ('Consumer Reports', 30, 'Consumer'),
            ('Local Programming', 120, 'Various')
        ]
    elif network in ['Light TV', 'Light']:
        schedule = [
            ('Highway to Heaven', 60, 'Family Drama'),
            ('Touched by an Angel', 60, 'Family Drama'),
            ('7th Heaven', 60, 'Family Drama'),
            ('The Waltons', 60, 'Family Drama'),
            ('Little House on the Prairie', 60, 'Family Drama'),
            ('Dr. Quinn Medicine Woman', 60, 'Family Drama'),
            ('Christy', 60, 'Family Drama'),
            ('Promised Land', 60, 'Family Drama'),
            ('Family Movies', 120, 'Movies'),
            ('Kids Programming', 120, 'Kids')
        ]
    elif network == 'Circle':
        schedule = [
            ('Country Music Videos', 60, 'Music'),
            ('CMT Crossroads', 60, 'Music'),
            ('Grand Ole Opry', 120, 'Music'),
            ('Country Countdown', 60, 'Music'),
            ('Acoustic Sessions', 60, 'Music'),
            ('Country Documentaries', 60, 'Documentary'),
            ('Nashville', 60, 'Drama'),
            ('Country Classics', 120, 'Music'),
            ('Opry Live', 120, 'Music')
        ]
    elif network == 'Decades':
        schedule = [
            ('50s Programming', 120, 'Nostalgia'),
            ('60s Programming', 120, 'Nostalgia'),
            ('70s Programming', 120, 'Nostalgia'),
            ('80s Programming', 120, 'Nostalgia'),
            ('90s Programming', 120, 'Nostalgia'),
            ('Retro Commercials', 30, 'Nostalgia'),
            ('Vintage Variety', 60, 'Variety'),
            ('Classic Sitcoms', 60, 'Comedy'),
            ('Retro Movies', 120, 'Movies')
        ]
    elif network == 'Story Television':
        schedule = [
            ('Classic Dramas', 60, 'Drama'),
            ('Family Stories', 60, 'Family'),
            ('Heartland Stories', 60, 'Family'),
            ('Period Dramas', 90, 'Drama'),
            ('Biographical Films', 120, 'Biography'),
            ('Historical Documentaries', 60, 'Documentary'),
            ('True Stories', 60, 'Biography'),
            ('Inspirational Movies', 120, 'Inspirational'),
            ('Classic Movies', 120, 'Movies')
        ]
    elif network == 'True Crime Network':
        schedule = [
            ('Dateline', 60, 'Crime'),
            ('48 Hours', 60, 'Crime'),
            ('20/20', 60, 'Crime'),
            ('Cold Case Files', 60, 'Crime'),
            ('The First 48', 60, 'Crime'),
            ('Forensic Files', 30, 'Crime'),
            ('Unsolved Mysteries', 60, 'Mystery'),
            ('Crime Stories', 60, 'Crime')
        ]
    elif network == 'Newsy':
        schedule = [
            ('Morning Newsy', 180, 'News'),
            ('Midday Update', 120, 'News'),
            ('Afternoon News', 180, 'News'),
            ('Evening Headlines', 120, 'News'),
            ('In-Depth', 60, 'News'),
            ('The Why', 30, 'News'),
            ('Newsy Tonight', 60, 'News'),
            ('Overnight News', 240, 'News')
        ]
    elif network == 'Rewind TV':
        schedule = [
            ('70s Sitcoms', 60, 'Comedy'),
            ('80s Sitcoms', 60, 'Comedy'),
            ('90s Sitcoms', 60, 'Comedy'),
            ('Classic Game Shows', 60, 'Game Show'),
            ('Variety Shows', 60, 'Variety'),
            ('Talk Shows', 60, 'Talk Show'),
            ('Retro Cartoons', 60, 'Animation'),
            ('Classic Movies', 120, 'Movies'),
            ('Family Movies', 120, 'Movies'),
            ('Kids Afternoon', 120, 'Kids'),
            ('Family Programming', 120, 'Family'),
            ('Evening Kids Shows', 120, 'Kids')
        ]
    elif network in ['TBN', 'Hillsong', 'JUCE TV', 'Enlace', 'TBN Salsa']:
        schedule = [
            ('Morning Worship', 120, 'Religious'),
            ('Teaching Program', 60, 'Religious'),
            ('Gospel Music', 90, 'Religious'),
            ('Ministry Hour', 60, 'Religious'),
            ('Evening Service', 120, 'Religious'),
            ('Late Night Prayer', 60, 'Religious'),
            ('Overnight Programming', 180, 'Religious')
        ]
    elif network in ['Shop', 'QVC', 'HSN']:
        schedule = [
            ('Morning Deals', 180, 'Shopping'),
            ('Afternoon Shopping', 180, 'Shopping'),
            ('Prime Time Deals', 180, 'Shopping'),
            ('Late Night Shopping', 180, 'Shopping'),
            ('Overnight Deals', 180, 'Shopping')
        ]
    elif network in ['ION Plus']:
        schedule = [
            ('NCIS Reruns', 60, 'Crime Drama'),
            ('Criminal Minds', 60, 'Crime Drama'),
            ('Chicago P.D.', 60, 'Crime Drama'),
            ('Law & Order SVU', 60, 'Crime Drama'),
            ('Blue Bloods', 60, 'Crime Drama'),
            ('CSI', 60, 'Crime Drama'),
            ('NCIS: New Orleans', 60, 'Crime Drama'),
            ('FBI', 60, 'Crime Drama')
        ]
    elif network == 'Independent':
        schedule = [
            ('Local Programming', 120, 'Various'),
            ('Syndicated Shows', 180, 'Various'),
            ('Movies', 120, 'Movies'),
            ('Talk Shows', 60, 'Talk Show'),
            ('Late Movies', 180, 'Movies')
        ]
    elif network == 'Create':
        schedule = [
            ('How-To Shows', 60, 'Educational'),
            ('Cooking Shows', 60, 'Cooking'),
            ('Home Improvement', 60, 'Lifestyle'),
            ('Arts & Crafts', 60, 'Educational'),
            ('Travel Shows', 60, 'Travel'),
            ('Gardening Shows', 60, 'Lifestyle'),
            ('DIY Programming', 60, 'Educational'),
            ('Educational Programming', 120, 'Educational')
        ]
    elif network == 'PBS Kids':
        schedule = [
            ('Sesame Street', 60, 'Children'),
            ('Daniel Tiger', 30, 'Children'),
            ('Wild Kratts', 30, 'Children'),
            ('Curious George', 30, 'Children'),
            ('Arthur', 30, 'Children'),
            ('Clifford', 30, 'Children'),
            ('Elinor Wonders Why', 30, 'Children'),
            ('Xavier Riddle', 30, 'Children'),
            ('Molly of Denali', 30, 'Children'),
            ('Educational Kids Shows', 60, 'Children')
        ]
    elif network in ['CBSN', 'CBS News']:
        schedule = [
            ('CBSN Live', 60, 'News'),
            ('Red & Blue', 60, 'News'),
            ('CBSN Originals', 30, 'News'),
            ('CBS Evening News', 30, 'News'),
            ('CBS This Morning', 180, 'News'),
            ('Face the Nation', 60, 'News'),
            ('60 Minutes', 60, 'News'),
            ('48 Hours', 60, 'News')
        ]
    elif network in ['Fave TV', 'Fave']:
        schedule = [
            ('Classic Movies', 120, 'Movies'),
            ('Feel Good Movies', 120, 'Movies'),
            ('Family Movies', 120, 'Movies'),
            ('Romantic Movies', 120, 'Movies'),
            ('Comedy Movies', 120, 'Movies'),
            ('Drama Movies', 120, 'Movies'),
            ('Holiday Movies', 120, 'Movies'),
            ('Favorite Films', 120, 'Movies')
        ]
    elif network in ['True Crime', 'True Crime Network']:
        schedule = [
            ('Forensic Files', 30, 'Crime'),
            ('Cold Case Files', 60, 'Crime'),
            ('The First 48', 60, 'Crime'),
            ('Snapped', 60, 'Crime'),
            ('Homicide Hunter', 60, 'Crime'),
            ('American Justice', 60, 'Crime'),
            ('City Confidential', 60, 'Crime'),
            ('Crime Documentaries', 60, 'Documentary')
        ]
    elif network == 'Oxygen':
        schedule = [
            ('Snapped', 60, 'Crime'),
            ('Dateline: Secrets Uncovered', 60, 'Crime'),
            ('Cold Justice', 60, 'Crime'),
            ('Criminal Confessions', 60, 'Crime'),
            ('Killer Couples', 60, 'Crime'),
            ('Murdered by Morning', 60, 'Crime'),
            ('True Crime Programming', 60, 'Crime'),
            ('Investigation Shows', 60, 'Crime')
        ]
    elif network in ['The 365', 'The365']:
        schedule = [
            ('Local Events', 30, 'Local'),
            ('Community News', 30, 'News'),
            ('Weather Updates', 30, 'Weather'),
            ('Sports Highlights', 30, 'Sports'),
            ('Entertainment News', 30, 'Entertainment'),
            ('Local Features', 60, 'Local'),
            ('Community Programming', 60, 'Local'),
            ('Regional Content', 60, 'Local')
        ]
    elif network in ['Independent', 'IND']:
        schedule = [
            ('Syndicated Programming', 120, 'Various'),
            ('Classic Movies', 120, 'Movies'),
            ('Local News', 30, 'News'),
            ('Talk Shows', 60, 'Talk Show'),
            ('Infomercials', 30, 'Shopping'),
            ('Religious Programming', 60, 'Religious'),
            ('Classic TV Shows', 60, 'Classic TV'),
            ('Independent Films', 120, 'Movies')
        ]
    elif network in ['Justice Network', 'Justice']:
        schedule = [
            ('In Session', 60, 'Court'),
            ('Justice with Judge Mablean', 30, 'Court'),
            ('Supreme Justice', 30, 'Court'),
            ('True Crime Programming', 60, 'Crime'),
            ('Police Documentaries', 60, 'Crime'),
            ('Court Cases', 60, 'Court'),
            ('Legal Programming', 60, 'Legal'),
            ('Crime Investigation', 60, 'Crime')
        ]
    elif network == 'Nosey':
        schedule = [
            ('Maury', 60, 'Talk Show'),
            ('Jerry Springer', 60, 'Talk Show'),
            ('Steve Wilkos', 60, 'Talk Show'),
            ('Cheaters', 30, 'Reality'),
            ('The Doctors', 60, 'Talk Show'),
            ('Judge Jerry', 30, 'Court Show'),
            ('Paternity Court', 30, 'Court Show'),
            ('Talk Show Marathon', 120, 'Talk Show')
        ]
    elif network in ['Movies! Gold', 'MSGold']:
        schedule = [
            ('Golden Age Movies', 120, 'Movies'),
            ('Classic Hollywood', 120, 'Movies'),
            ('Vintage Cinema', 120, 'Movies'),
            ('Film Noir', 120, 'Movies'),
            ('Classic Westerns', 120, 'Movies'),
            ('Hollywood Classics', 120, 'Movies'),
            ('Timeless Movies', 120, 'Movies'),
            ('Cinema Treasures', 120, 'Movies')
        ]
    elif network in ['ION Plus', 'IONPLUS']:
        schedule = [
            ('Leverage', 60, 'Crime Drama'),
            ('Psych', 60, 'Comedy Drama'),
            ('Monk', 60, 'Mystery'),
            ('White Collar', 60, 'Crime Drama'),
            ('Burn Notice', 60, 'Action'),
            ('The Closer', 60, 'Crime Drama'),
            ('Major Crimes', 60, 'Crime Drama'),
            ('ION Programming', 60, 'Various')
        ]
    elif network in ['ION Mystery', 'Mystery']:
        schedule = [
            ('Columbo', 120, 'Mystery'),
            ('Perry Mason', 60, 'Mystery'),
            ('Matlock', 60, 'Mystery'),
            ('Murder, She Wrote', 60, 'Mystery'),
            ('Quincy M.E.', 60, 'Mystery'),
            ('McMillan & Wife', 90, 'Mystery'),
            ('McCloud', 90, 'Mystery'),
            ('Classic Mystery Movies', 120, 'Mystery')
        ]
    elif network in ['TruTV', 'BUSTED']:
        schedule = [
            ('Impractical Jokers', 30, 'Comedy'),
            ('The Carbonaro Effect', 30, 'Comedy'),
            ('truTV Top Funniest', 60, 'Comedy'),
            ('World\'s Dumbest', 60, 'Comedy'),
            ('Hardcore Pawn', 30, 'Reality'),
            ('Storage Hunters', 30, 'Reality'),
            ('Comedy Programming', 60, 'Comedy'),
            ('Reality Shows', 60, 'Reality')
        ]
    elif network in ['HSN', 'HSN2']:
        schedule = [
            ('Home Shopping', 60, 'Shopping'),
            ('Fashion Hour', 60, 'Shopping'),
            ('Jewelry Showcase', 60, 'Shopping'),
            ('Electronics Sale', 60, 'Shopping'),
            ('Beauty Products', 60, 'Shopping'),
            ('Kitchen Essentials', 60, 'Shopping'),
            ('Health & Wellness', 60, 'Shopping'),
            ('Special Deals', 60, 'Shopping')
        ]
    elif network == 'QVC':
        schedule = [
            ('Today\'s Special Value', 60, 'Shopping'),
            ('Fashion Focus', 60, 'Shopping'),
            ('Beauty iQ', 60, 'Shopping'),
            ('Electronics Show', 60, 'Shopping'),
            ('Jewelry Gallery', 60, 'Shopping'),
            ('For the Home', 60, 'Shopping'),
            ('Kitchen & Food', 60, 'Shopping'),
            ('QVC Programming', 60, 'Shopping')
        ]
    elif network in ['Shop LC', 'ShopLC']:
        schedule = [
            ('Jewelry Auction', 60, 'Shopping'),
            ('Gemstone Collection', 60, 'Shopping'),
            ('Designer Jewelry', 60, 'Shopping'),
            ('Liquidation Channel', 60, 'Shopping'),
            ('Precious Metals', 60, 'Shopping'),
            ('Fine Jewelry', 60, 'Shopping'),
            ('Jewelry Specials', 60, 'Shopping'),
            ('Auction Programming', 60, 'Shopping')
        ]
    elif network in ['TBN', 'TBN HD']:
        schedule = [
            ('Praise', 120, 'Religious'),
            ('Joyce Meyer', 30, 'Religious'),
            ('Joel Osteen', 60, 'Religious'),
            ('Behind the Scenes', 30, 'Religious'),
            ('TBN Presents', 60, 'Religious'),
            ('Christian Movies', 120, 'Religious'),
            ('Worship Services', 90, 'Religious'),
            ('Religious Programming', 60, 'Religious')
        ]
    elif network in ['Merit Street', 'Merit']:
        schedule = [
            ('Educational Programming', 60, 'Educational'),
            ('Family Shows', 60, 'Family'),
            ('Inspirational Programming', 60, 'Inspirational'),
            ('Community Focus', 30, 'Community'),
            ('Merit Programming', 60, 'Educational'),
            ('Youth Programming', 60, 'Youth'),
            ('Local Community', 60, 'Local'),
            ('Educational Content', 60, 'Educational')
        ]
    elif network == 'Inspire':
        schedule = [
            ('Inspirational Movies', 120, 'Movies'),
            ('Family Programming', 60, 'Family'),
            ('Faith & Family', 60, 'Religious'),
            ('Uplifting Stories', 60, 'Inspirational'),
            ('Christian Movies', 120, 'Religious'),
            ('Family Values', 60, 'Family'),
            ('Positive Programming', 60, 'Inspirational'),
            ('Faith-Based Shows', 60, 'Religious')
        ]
    elif network == 'ONTV4U':
        schedule = [
            ('Local Programming', 60, 'Local'),
            ('Community Events', 30, 'Community'),
            ('Regional News', 30, 'News'),
            ('Local Features', 60, 'Local'),
            ('Public Access', 30, 'Public Access'),
            ('Community Focus', 60, 'Community'),
            ('Local Content', 60, 'Local'),
            ('Regional Programming', 60, 'Regional')
        ]
    elif network == 'Positiv':
        schedule = [
            ('Positive Programming', 60, 'Inspirational'),
            ('Uplifting Content', 60, 'Inspirational'),
            ('Family Shows', 60, 'Family'),
            ('Motivational Programming', 60, 'Motivational'),
            ('Feel Good Shows', 60, 'Positive'),
            ('Inspirational Movies', 120, 'Movies'),
            ('Life Enhancement', 60, 'Lifestyle'),
            ('Positive Living', 60, 'Lifestyle')
        ]
    elif network in ['Univision', 'WLTV']:
        schedule = [
            ('Despierta América', 240, 'Spanish News'),
            ('El Gordo y la Flaca', 60, 'Spanish Entertainment'),
            ('Noticiero Univision', 30, 'Spanish News'),
            ('Primer Impacto', 60, 'Spanish News'),
            ('Telenovelas', 120, 'Spanish Drama'),
            ('Sábado Gigante', 240, 'Spanish Variety'),
            ('Fútbol', 120, 'Spanish Sports'),
            ('Spanish Programming', 60, 'Spanish')
        ]
    elif network in ['Telemundo', 'WSCV']:
        schedule = [
            ('Un Nuevo Día', 240, 'Spanish News'),
            ('Al Rojo Vivo', 60, 'Spanish News'),
            ('Noticias Telemundo', 30, 'Spanish News'),
            ('Caso Cerrado', 60, 'Spanish Court'),
            ('Telenovelas', 120, 'Spanish Drama'),
            ('Deportes Telemundo', 60, 'Spanish Sports'),
            ('Spanish Movies', 120, 'Spanish Movies'),
            ('Spanish Programming', 60, 'Spanish')
        ]
    elif network in ['Exitos', 'EXITOS']:
        schedule = [
            ('Música Regional', 60, 'Spanish Music'),
            ('Programación Musical', 60, 'Spanish Music'),
            ('Videos Musicales', 120, 'Spanish Music'),
            ('Conciertos', 120, 'Spanish Music'),
            ('Entretenimiento Musical', 60, 'Spanish Entertainment'),
            ('Hit Music', 60, 'Spanish Music'),
            ('Spanish Music Videos', 60, 'Spanish Music'),
            ('Music Programming', 60, 'Spanish Music')
        ]
    elif network in ['NBC Universo', 'WSCV-PB']:
        schedule = [
            ('Deportes NBC Universo', 60, 'Spanish Sports'),
            ('Fútbol Premier League', 120, 'Spanish Sports'),
            ('Boxing', 180, 'Spanish Sports'),
            ('Wrestling WWE', 120, 'Spanish Sports'),
            ('Spanish Sports News', 30, 'Spanish Sports'),
            ('Olympic Programming', 120, 'Spanish Sports'),
            ('Spanish Sports', 120, 'Spanish Sports'),
            ('Sports Programming', 60, 'Spanish Sports')
        ]
    elif network == 'Story Television':
        schedule = [
            ('Heartwarming Stories', 60, 'Drama'),
            ('Family Movies', 120, 'Movies'),
            ('Inspirational Stories', 60, 'Inspirational'),
            ('Classic Family Shows', 60, 'Family'),
            ('Feel-Good Programming', 60, 'Family'),
            ('Uplifting Movies', 120, 'Movies'),
            ('Family Drama', 60, 'Drama'),
            ('Story Programming', 60, 'Drama')
        ]
    elif network == 'Newsy':
        schedule = [
            ('Morning News', 180, 'News'),
            ('Newsy Today', 60, 'News'),
            ('The Why', 30, 'News'),
            ('Newsy Reports', 30, 'News'),
            ('Breaking News', 30, 'News'),
            ('News Analysis', 60, 'News'),
            ('In Depth', 60, 'News'),
            ('News Programming', 60, 'News')
        ]
    elif network == 'Rewind TV':
        schedule = [
            ('Classic TV Shows', 60, 'Classic TV'),
            ('Retro Programming', 60, 'Classic TV'),
            ('Vintage Series', 60, 'Classic TV'),
            ('Old School Shows', 60, 'Classic TV'),
            ('TV Classics', 60, 'Classic TV'),
            ('Nostalgic Programming', 60, 'Classic TV'),
            ('Classic Comedy', 60, 'Classic Comedy'),
            ('Vintage Entertainment', 60, 'Classic TV')
        ]
    elif network == 'Quest':
        schedule = [
            ('Adventure Shows', 60, 'Adventure'),
            ('Survival Programming', 60, 'Reality'),
            ('Nature Documentaries', 60, 'Documentary'),
            ('Exploration Shows', 60, 'Adventure'),
            ('Quest Programming', 60, 'Adventure'),
            ('Outdoor Adventures', 60, 'Adventure'),
            ('Discovery Shows', 60, 'Documentary'),
            ('Adventure Programming', 60, 'Adventure')
        ]
    else:
        # Default generic schedule for any unlisted networks
        schedule = [
            ('Morning Show', 180, 'Various'),
            ('Daytime Programming', 240, 'Various'),
            ('Prime Time', 180, 'Various'),
            ('Late Night', 180, 'Various')
        ]
    
    return schedule

def create_xmltv(channels, programmes):
    """Create XMLTV formatted data."""
    doc = xml.dom.minidom.Document()
    tv = doc.createElement("tv")
    tv.setAttribute("generator-info-name", "Custom EPG Grabber")
    tv.setAttribute("generator-info-url", "http://localhost:8000")
    doc.appendChild(tv)
    
    # Add channels
    for channel_id, channel_info in channels.items():
        channel_elem = doc.createElement("channel")
        channel_elem.setAttribute("id", str(channel_id))
        
        display_name = doc.createElement("display-name")
        display_name.appendChild(doc.createTextNode(channel_info['name']))
        channel_elem.appendChild(display_name)
        
        tv.appendChild(channel_elem)
    
    # Add programmes
    for programme in programmes:
        programme_elem = doc.createElement("programme")
        programme_elem.setAttribute("start", programme['start'])
        programme_elem.setAttribute("stop", programme['stop'])
        programme_elem.setAttribute("channel", str(programme['channel']))
        
        title = doc.createElement("title")
        title.setAttribute("lang", "en")
        title.appendChild(doc.createTextNode(programme['title']))
        programme_elem.appendChild(title)
        
        desc = doc.createElement("desc")
        desc.setAttribute("lang", "en")
        desc.appendChild(doc.createTextNode(programme['desc']))
        programme_elem.appendChild(desc)
        
        category = doc.createElement("category")
        category.setAttribute("lang", "en")
        category.appendChild(doc.createTextNode(programme['category']))
        programme_elem.appendChild(category)
        
        tv.appendChild(programme_elem)
    
    # Return pretty formatted XML
    return doc.toprettyxml(indent="  ", encoding=None)

def grab_epg():
    """Main EPG generation function."""
    print("Starting EPG generation...")
    
    programmes = []
    
    for channel_id, channel_info in CHANNELS.items():
        print(f"Processing channel {channel_id}: {channel_info['name']}")
        
        # Generate schedule for 3 days
        current_time = datetime.now()
        for day in range(3):
            day_start = current_time.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=day)
            
            # Get fallback schedule based on network type
            network = channel_info.get('network', 'Generic')
            schedule = get_fallback_schedule(network)
            
            current_show_start = day_start
            
            # Generate programmes for this day
            programmes_for_day = []
            while current_show_start < day_start + timedelta(hours=18):  # 18 hours of programming per day
                for show_name, duration, category in schedule:
                    if current_show_start >= day_start + timedelta(hours=18):
                        break
                        
                    programme = {
                        'start': current_show_start.strftime('%Y%m%d%H%M%S +0000'),
                        'stop': (current_show_start + timedelta(minutes=duration)).strftime('%Y%m%d%H%M%S +0000'),
                        'channel': channel_id,
                        'title': show_name,
                        'desc': f"{show_name} on {channel_info['name']}",
                        'category': category
                    }
                    programmes.append(programme)
                    programmes_for_day.append(programme)
                    current_show_start += timedelta(minutes=duration)
            
            print(f"  Day {day + 1}: Generated {len(programmes_for_day)} programmes")
    
    print(f"Total programmes generated: {len(programmes)}")
    
    # Create XMLTV data
    xmltv_data = create_xmltv(CHANNELS, programmes)
    
    # Write to file
    output_file = '/app/guide.xml'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(xmltv_data)
    
    print(f"EPG data written to {output_file}")
    return output_file

def main():
    """Main function."""
    try:
        grab_epg()
        print("EPG generation completed successfully!")
    except Exception as e:
        print(f"Error generating EPG: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
