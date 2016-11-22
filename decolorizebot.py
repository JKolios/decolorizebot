import shelve
import logging
import os
import urllib.parse

import requests
import PIL.Image
import imgurpython
import prawbot.bots
from prawbot.utils.url_finder import find_urls

log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler())
log.setLevel(logging.DEBUG)

BOT_CLIENT_ID = os.environ.get('BOT_CLIENT_ID')
BOT_CLIENT_SECRET = os.environ.get('BOT_CLIENT_SECRET')
IMGUR_CLIENT_ID = os.environ.get('IMGUR_CLIENT_ID')
IMGUR_CLIENT_SECRET = os.environ.get('IMGUR_CLIENT_SECRET')

BOT_REDIRECT_URI = "http://127.0.0.1:65010/authorize_callback"
BOT_USER_AGENT = "Decolorizer by /u/much_reddit_so_amaze"


class DecolorizeBot(prawbot.bots.CommentStreamBot):
    def __init__(self, api_client=None):
        self.imgur_client = None
        self.comments_done = []
        self.urls_done = []
        super().__init__(api_client=api_client)

    def configure(self, *args, **kwargs):
        self.subreddit = kwargs['subreddit']
        self.imgur_client = imgurpython.ImgurClient(client_id=IMGUR_CLIENT_ID,
                                                    client_secret=IMGUR_CLIENT_SECRET)

        with shelve.open('decolorize_storage') as decolorize_storage:
            self.comments_done = decolorize_storage.get('comments_done', [])
            self.urls_done = decolorize_storage.get('urls_done', [])

        log.info('Loaded comments_done:{0}'.format(self.comments_done))
        log.info('Loaded urls_done:{0}'.format(self.urls_done))

    @staticmethod
    def condition_met(comment_text):
        return comment_text.lower().startswith('decolorizebot')

    @staticmethod
    def extract_filename(url):
        url_path = urllib.parse.urlparse(url).path
        last_element = url_path.split('/')[-1]
        return last_element

    @classmethod
    def save_image(cls, url, filename):
        request = requests.get(url, stream=True)
        if request.status_code == 200:

            saved_filename = 'images/' + filename

            with open(saved_filename, 'wb') as f:
                request.raw.decode_content = True
                for chunk in request.iter_content(8192):
                    f.write(chunk)
            log.info('Saved image: {0}'.format(saved_filename))
            return saved_filename
        else:
            return None

    @staticmethod
    def decolorize_image(in_filename, out_filename):
        try:
            img_obj = PIL.Image.open(in_filename)
        except IOError:
            log.info('File {0} is not an image file'.format(in_filename))
            return False
        img_obj = img_obj.convert(mode='L')

        try:
            img_obj.save(out_filename, format='JPEG')
        except IOError:
            log.info('File {0} could not be written'.format(out_filename))
            return False

        return True

    def handle_image_url(self, url):
        filename = self.extract_filename(url)

        saved_filename = self.save_image(url, filename)

        if not saved_filename:
            return

        processed_filename = 'processed/' + filename

        if self.decolorize_image(in_filename=saved_filename,
                                 out_filename=processed_filename):
            log.info('Successfully decolorized: {0}'.format(processed_filename))
        else:
            log.info('Failed to decolorize: {0}'.format(processed_filename))
            return

        upload_result = self.imgur_client.upload_from_path(processed_filename)

        return upload_result.get('link')

    @staticmethod
    def generate_reply(urls):
        reply = "Who needs color?"
        for url in urls:
            reply += '\n{url}'.format(url=url)

        return reply

    def exit_handler(self):
        with shelve.open('decolorize_storage') as decolorize_storage:
            decolorize_storage['comments_done'] = self.comments_done
            decolorize_storage['urls_done'] = self.urls_done
        log.info('Saved comments_done: {0}'.format(self.comments_done))
        log.info('Saved urls_done: {0}'.format(self.urls_done))

    def func(self, comment, *args, **kwargs):
        if comment.id not in self.comments_done and self.condition_met(comment.body):
            log.info('Condition met: {0}'.format(comment.body))
            comment_urls = find_urls(comment.body)
            log.info('Comment URLs: {0}'.format(comment_urls))

            reply_urls = []
            for url in comment_urls:
                if url in self.urls_done:
                    continue
                reply_url = self.handle_image_url(url)
                if reply_url:
                    reply_urls.append(reply_url)
                    self.urls_done.append(reply_url)
            if not reply_urls:
                # If no URLs exist within the comment body, try the submission's URL
                if comment.submission.url:
                    reply_url = self.handle_image_url(comment.submission.url)
                    if reply_url:
                        reply_urls.append(reply_url)
                        self.urls_done.append(reply_url)

            log.info('Reply URLS: {0}'.format(reply_urls))

            if reply_urls:
                reply_body = self.generate_reply(reply_urls)
                log.info('Reply Body: {0}'.format(reply_body))
                comment.reply(reply_body)
                log.info('Replied.')

            self.comments_done.append(comment.id)

decolorize_bot =prawbot.create_bot(BOT_USER_AGENT,
                                   BOT_CLIENT_ID,
                                   BOT_CLIENT_SECRET,
                                   BOT_REDIRECT_URI,
                                   ['identity', 'read', 'submit'],
                                   DecolorizeBot,
                                   subreddit='greece')
decolorize_bot.run()


