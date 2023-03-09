# encoding:utf-8

"""
wechat channel
"""
import itchat
import json
import os
from itchat.content import *
from channel.channel import Channel
from concurrent.futures import ThreadPoolExecutor
from common.log import logger
from common import const
from config import channel_conf_val, channel_conf
import requests
import io

thread_pool = ThreadPoolExecutor(max_workers=8)


@itchat.msg_register(TEXT)
def handler_single_msg(msg):
    WechatChannel().handle(msg)
    return None


@itchat.msg_register(TEXT, isGroupChat=True)
def handler_group_msg(msg):
    WechatChannel().handle_group(msg)
    return None


class WechatChannel(Channel):
    def __init__(self):
        pass

    def startup(self):
        # login by scan QRCode
        itchat.auto_login(enableCmdQR=2)

        # start message listener
        itchat.run()

    def handle(self, msg):
        logger.debug("[WX]receive msg: " + json.dumps(msg, ensure_ascii=False))
        from_user_id = msg['FromUserName']
        content = msg['Text']

        # 检测敏感词
        sensitive_words_file = 'sensitive_words.txt'
        if os.path.isfile(sensitive_words_file):
            with open(sensitive_words_file, 'r', encoding='utf-8') as f:
                sensitive_words = [word.strip() for word in f.readlines()]
            for word in sensitive_words:
                if word in content:
                    self.send("你输入的内容包含敏感词汇", from_user_id)
                    return

        to_user_id = msg['ToUserName']              # 接收人id
        other_user_id = msg['User']['UserName']     # 对手方id
        match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'single_chat_prefix'))
        if from_user_id == other_user_id and match_prefix is not None:
            # 好友向自己发送消息
            if match_prefix != '':
                str_list = content.split(match_prefix, 1)
                if len(str_list) == 2:
                    content = str_list[1].strip()

            img_match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'image_create_prefix'))
            if img_match_prefix:
                content = content.split(img_match_prefix, 1)[1].strip()
                thread_pool.submit(self._do_send_img, content, from_user_id)
            else:
                thread_pool.submit(self._do_send, content, from_user_id)

        elif to_user_id == other_user_id and match_prefix:
            # 自己给好友发送消息
            str_list = content.split(match_prefix, 1)
            if len(str_list) == 2:
                content = str_list[1].strip()
            img_match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'image_create_prefix'))
            if img_match_prefix:
                content = content.split(img_match_prefix, 1)[1].strip()
                thread_pool.submit(self._do_send_img, content, to_user_id)
            else:
                # 回复消息检测敏感词
                reply_content = self.build_reply_content(content)
                sensitive_words_file = 'sensitive_words.txt'
                if os.path.isfile(sensitive_words_file):
                    with open(sensitive_words_file, 'r', encoding='utf-8') as f:
                        sensitive_words = [word.strip() for word in f.readlines()]
                    for word in sensitive_words:
                        if word in reply_content:
                            self.send("请不要引导机器人做坏事", to_user_id)
                            return

                thread_pool.submit(self._do_send, reply_content, to_user_id)


    def handle_group(self, msg):
        logger.debug("[WX]receive group msg: " + json.dumps(msg, ensure_ascii=False))
        from_user_id = msg['FromUserName']
        content = msg['Text']

        # 检测敏感词
        sensitive_words_file = 'sensitive_words.txt'
        if os.path.isfile(sensitive_words_file):
            with open(sensitive_words_file, 'r', encoding='utf-8') as f:
                sensitive_words = [word.strip() for word in f.readlines()]
            for word in sensitive_words:
                if word in content:
                    self.send("你输入的内容包含敏感词汇", from_user_id)
                    return

        to_group_id = msg['ToUserName']              # 群组id
        match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'group_chat_prefix'))
        if match_prefix is not None:
            # 自己在群组里发送消息
            str_list = content.split(match_prefix, 1)
            if len(str_list) == 2:
                content = str_list[1].strip()

            img_match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'image_create_prefix'))
            if img_match_prefix:
                content = content.split(img_match_prefix, 1)[1].strip()
                thread_pool.submit(self._do_send_img_group, content, to_group_id)
            else:
                # 回复消息检测敏感词
                reply_content = self.build_reply_content(content)
                sensitive_words_file = 'sensitive_words.txt'
                if os.path.isfile(sensitive_words_file):
                    with open(sensitive_words_file, 'r', encoding='utf-8') as f:
                        sensitive_words = [word.strip() for word in f.readlines()]
                    for word in sensitive_words:
                        if word in reply_content:
                            self.send("请不要引导机器人做坏事", to_group_id)
                            return

                thread_pool.submit(self._do_send_group, reply_content, to_group_id)
        elif msg['isAt']:
            # 机器人被@了
            str_list = content.split('@' + msg['User']['NickName'], 1)
            if len(str_list) == 2:
                content = str_list[1].strip()
            match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'single_chat_prefix'))
            if match_prefix is not None:
                # 自己在群组里回复某人的消息
                str_list = content.split(match_prefix, 1)
                if len(str_list) == 2:
                    content = str_list[1].strip()

            img_match_prefix = self.check_prefix(content, channel_conf_val(const.WECHAT, 'image_create_prefix'))
            if img_match_prefix:
                content = content.split(img_match_prefix, 1)[1].strip()
                at_user_id = msg['ActualUserName']
                thread_pool.submit(self._do_send_img, content, at_user_id)
            else:
                at_user_id = msg['ActualUserName']
                thread_pool.submit(self._do_send, content, at_user_id)


    def send(self, msg, receiver):
        logger.info('[WX] sendMsg={}, receiver={}'.format(msg, receiver))
        itchat.send(msg, toUserName=receiver)

    def _do_send(self, query, reply_user_id):
        try:
            if not query:
                return
            context = dict()
            context['from_user_id'] = reply_user_id
            reply_text = super().build_reply_content(query, context)
            if reply_text:
                self.send(channel_conf_val(const.WECHAT, "single_chat_reply_prefix") + reply_text, reply_user_id)
        except Exception as e:
            logger.exception(e)

    def _do_send_img(self, query, reply_user_id):
        try:
            if not query:
                return
            context = dict()
            context['type'] = 'IMAGE_CREATE'
            img_url = super().build_reply_content(query, context)
            if not img_url:
                return

            # 图片下载
            pic_res = requests.get(img_url, stream=True)
            image_storage = io.BytesIO()
            for block in pic_res.iter_content(1024):
                image_storage.write(block)
            image_storage.seek(0)

            # 图片发送
            logger.info('[WX] sendImage, receiver={}'.format(reply_user_id))
            itchat.send_image(image_storage, reply_user_id)
        except Exception as e:
            logger.exception(e)

    def _do_send_group(self, query, msg):
        if not query:
            return
        context = dict()
        context['from_user_id'] = msg['ActualUserName']
        reply_text = super().build_reply_content(query, context)
        if reply_text:
            reply_text = '@' + msg['ActualNickName'] + ' ' + reply_text.strip()
            self.send(channel_conf_val(const.WECHAT, "group_chat_reply_prefix", "") + reply_text, msg['User']['UserName'])


    def check_prefix(self, content, prefix_list):
        for prefix in prefix_list:
            if content.startswith(prefix):
                return prefix
        return None


    def check_contain(self, content, keyword_list):
        if not keyword_list:
            return None
        for ky in keyword_list:
            if content.find(ky) != -1:
                return True
        return None
