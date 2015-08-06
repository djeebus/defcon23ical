import datetime
import os
import re
import requests
import time
import pytz
vegas = pytz.timezone('US/Pacific')

import win_unicode_console
win_unicode_console.enable()

here = os.path.dirname(os.path.abspath(__file__))
DEFCON_SCHEDULE_PATH = os.path.join(here, 'schedule.html')
DEFCON_SCHEDULE_URL = 'https://www.defcon.org/html/defcon-23/dc-23-schedule.html'
DEFCON_SPEAKERS_PATH = os.path.join(here, 'speakers.html')
DEFCON_SPEAKERS_URL = 'https://www.defcon.org/html/defcon-23/dc-23-speakers.html'
DEFCON_ICAL_PATH = os.path.join(here, 'defcon23.ics')


def get_url(url, path):
    if not os.path.isfile(path):
        print("%s => %s" % (url, path))
        response = requests.get(url, stream=True)
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if not chunk:  # keep-alive
                    continue

                f.write(chunk)
            f.flush()

    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    return ' '.join(lines)


dates = {
    'Thursday': datetime.date(2015, 8, 6),
    'Friday': datetime.date(2015, 8, 7),
    'Saturday': datetime.date(2015, 8, 8),
    'Sunday': datetime.date(2015, 8, 9),
}


def mkdate(day, tm):
    return datetime.datetime.combine(dates[day], tm)


chars = re.compile(r'[^a-z^0-9]', re.IGNORECASE)
def clean_title(title):
    return chars.sub('', title.lower())


schedule_content = get_url(DEFCON_SCHEDULE_URL,
                           DEFCON_SCHEDULE_PATH)

speakers_content = get_url(DEFCON_SPEAKERS_URL,
                           DEFCON_SPEAKERS_PATH)


from lxml import etree
parser = etree.HTMLParser(encoding='utf-8')
tree = etree.fromstring(schedule_content, parser)

presentations_by_day_track = {}
presentations_by_title = {}
for day in tree.xpath('//h2[@class="category"]'):
    day_name = day.text
    presentations_by_day_track.setdefault(day_name, {})

    for p_time in day.itersiblings():
        if p_time.tag == 'h2':
            break

        if p_time.tag != 'h3':
            continue

        time_text = p_time.text

        track_wrapper = p_time.getnext()
        for li in track_wrapper.getchildren():
            try:
                track = next(li.iterchildren('h4'))
            except StopIteration:
                continue

            track_text = track.text
            track_schedule = presentations_by_day_track[day_name].setdefault(track.text, [])

            if li.get('class') == 'emptyRoom':
                track_schedule.append(None)
                continue

            track_iter = track.itersiblings('p')

            title = next(track_iter)

            try:
                title = next(title.iterchildren('a'))
            except StopIteration:
                pass

            title_text = title.text
            title_href = title.get('href')

            speaker = next(track_iter)

            # print("\t\tTRACK: %s" % track.text)
            # print("\t\t\t%s: %s" % (title_text, speaker.text))
            # print(speaker.text)

            start = time.strptime(time_text, '%H:%M')
            start = datetime.time(start.tm_hour, start.tm_min, tzinfo=vegas)
            start = mkdate(day_name, start)

            presentation = {
                'start': start,
                'title': title_text,
                'speaker': speaker.text,
            }

            track_schedule.append(presentation)
            presentations_by_title[clean_title(title_text)] = presentation


parser = etree.HTMLParser(encoding='utf-8')
tree = etree.fromstring(speakers_content, parser)

for article in tree.xpath('//article'):
    try:
        title = next(article.iterchildren('h2'))
    except StopIteration:
        continue

    title_text = title.text
    if not title_text:
        continue

    if title_text == 'DEF CON 101: The Panel.':
        title_text = 'DEF CON 101: The Panel'
    elif title_text == 'Introduction to SDR and the Wireless Village':
        title_text = 'Introduction to SDR and the Wireless Village'
    elif title_text == 'Key-Logger, Video, Mouse — How To Turn Your KVM Into a Raging Key-logging Monster':
        title_text = 'Key-Logger, Video, Mouse — How To Turn Your KVM Into a Raging Key-logging'

    print("%s ==> %s" % (title_text, clean_title(title_text)))
    presentation = presentations_by_title[clean_title(title_text)]

    presentation['details'] = ''.join(article.itertext())


import icalendar

calendar = icalendar.Calendar()
calendar.add('prodid', '-//DefCon 23 Schedule//defcon.org//')
calendar.add('version', '2.0')

for day, tracks in presentations_by_day_track.items():
    print("%s: %s tracks" % (day, len(tracks)))
    for track, sched in tracks.items():
        print("\t%s events" % len(sched))

        for index, presentation in enumerate(sched):
            if presentation is None:
                continue

            next_presentation = sched[index + 1] if len(sched) >= index + 2 else None
            if next_presentation and next_presentation['title'] == presentation['title']:
                continue

            prev_presentation = sched[index - 1] if index > 0 else None

            event = icalendar.Event()
            event['location'] = icalendar.vText(track)
            event.add('summary', presentation['title'])
            details = presentation.get('details')
            if details:
                event.add('DESCRIPTION', presentation['details'])
            else:
                print("missing desc: %s" % presentation['title'])

            if prev_presentation and prev_presentation['title'] == presentation['title']:
                start = prev_presentation['start']
            else:
                start = presentation['start']
            event.add('dtstart', start)

            if next_presentation is not None:
                end = next_presentation['start']
                event.add('dtend', end)

            if 'dtend' not in event:
                event.add('dtend', start + datetime.timedelta(hours=1))

            calendar.add_component(event)

with open(DEFCON_ICAL_PATH, 'wb') as f:
    f.write(calendar.to_ical())
    f.flush()