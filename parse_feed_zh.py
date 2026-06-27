import xml.etree.ElementTree as ET
import json, re, os, urllib.request, urllib.parse
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

YOUTUBE_API_KEY    = os.environ.get('YOUTUBE_API_KEY', '')
SERMON_PLAYLIST_ID = 'PLHaDvAO4RKLLlOG4nMxzCAs6IkAs3ZaMu'

def api_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def get_playlist_videos(api_key, playlist_id):
    videos = {}
    page_token = ''
    while True:
        params = urllib.parse.urlencode({
            'part': 'snippet',
            'playlistId': playlist_id,
            'maxResults': 50,
            'key': api_key,
            **({'pageToken': page_token} if page_token else {}),
        })
        try:
            data = api_get('https://www.googleapis.com/youtube/v3/playlistItems?' + params)
        except Exception as e:
            print(f'  Warning: {e}')
            break
        for item in data.get('items', []):
            snip   = item['snippet']
            vid_id = snip['resourceId']['videoId']
            title  = snip['title'].strip()
            pub    = snip.get('publishedAt', '')
            year_m = re.search(r'(20\d{2})', pub)
            videos[vid_id] = (title, year_m.group(1) if year_m else '')
        page_token = data.get('nextPageToken', '')
        if not page_token:
            break
    return videos

def best_match(query, playlist_videos, pub_date_str=''):
    def normalise(s):
        s = s.lower()
        s = re.sub(r'\|.*', '', s)
        s = re.sub(r'[^\w\s]', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    pub_year = None
    if pub_date_str:
        m = re.search(r'\b(20\d{2})\b', pub_date_str)
        if m:
            pub_year = m.group(1)

    stopwords = {'the','a','an','of','in','on','at','to','and','or','is','it','be','as','by','for','with'}
    q_words = set(normalise(query).split()) - stopwords
    if not q_words:
        return '', ''

    best_score, best_id, best_title = 0.0, '', ''
    for vid_id, (title, vid_year) in playlist_videos.items():
        t_words = set(normalise(title).split()) - stopwords
        if not t_words:
            continue
        overlap = len(q_words & t_words)
        if overlap == 0:
            continue
        score = overlap / len(q_words | t_words)
        if pub_year and vid_year:
            score *= 1.6 if pub_year == vid_year else 0.3
        if score > best_score:
            best_score, best_id, best_title = score, vid_id, title

    if best_score >= 0.25:
        print(f'    Matched: "{best_title}" (score {best_score:.2f})')
        return f'https://www.youtube.com/watch?v={best_id}', best_id
    return '', ''

# Parse RSS
tree = ET.parse('feed-zh.xml')
root = tree.getroot()
channel_el = root.find('channel')

channel_image = ''
ch_img = channel_el.find('image')
if ch_img is not None:
    url_el = ch_img.find('url')
    if url_el is not None:
        channel_image = (url_el.text or '').strip()
itunes_ch_img = channel_el.find('itunes:image', NS)
if itunes_ch_img is not None:
    channel_image = itunes_ch_img.get('href', channel_image)

# Load YouTube playlist
playlist_videos = {}
if YOUTUBE_API_KEY:
    print(f'Fetching Mandarin playlist ({SERMON_PLAYLIST_ID})...')
    playlist_videos = get_playlist_videos(YOUTUBE_API_KEY, SERMON_PLAYLIST_ID)
    print(f'  {len(playlist_videos)} videos')
else:
    print('No YOUTUBE_API_KEY — skipping YouTube matching')

items = []
for idx, item in enumerate(channel_el.findall('item')):
    def gt(tag):
        el = item.find(tag)
        return (el.text or '').strip() if el is not None else ''
    def gi(tag):
        el = item.find('itunes:' + tag, NS)
        return (el.text or '').strip() if el is not None else ''

    raw_title    = gt('title')
    pipe_parts   = raw_title.split('|')
    title        = pipe_parts[0].strip()
    title_series = pipe_parts[-1].strip() if len(pipe_parts) > 1 else ''
    pub_date     = gt('pubDate')

    enc       = item.find('enclosure')
    audio_url = enc.get('url', '') if enc is not None else ''
    raw_html  = gi('summary') or gt('description')
    desc      = re.sub(r'<[^>]+>', ' ', raw_html).strip()
    ep_img    = item.find('itunes:image', NS)
    image     = ep_img.get('href', '') if ep_img is not None else ''

    video_url, video_id = '', ''
    if playlist_videos:
        print(f'Matching: "{title}" ({pub_date})')
        video_url, video_id = best_match(title, playlist_videos, pub_date)

    items.append({
        'id': idx, 'title': title, 'titleSeries': title_series,
        'desc': desc, 'rawHtml': raw_html, 'pubDate': pub_date,
        'audioUrl': audio_url, 'link': gt('link'),
        'duration': gi('duration'), 'speaker': gi('author'),
        'image': image, 'videoUrl': video_url, 'videoId': video_id,
    })

output = {
    'channelImage': channel_image,
    'items': items,
    'updated': datetime.utcnow().isoformat() + 'Z',
}
with open('feed-zh.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False)

print(f'\nDone. {len(items)} Mandarin sermons, {sum(1 for i in items if i["videoId"])} YouTube matches.')
