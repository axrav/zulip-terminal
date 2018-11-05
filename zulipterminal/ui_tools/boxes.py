from collections import defaultdict
from time import ctime
from datetime import datetime
from typing import Any, Dict, List, Tuple, Union, Optional

import emoji
import urwid
from urwid_readline import ReadlineEdit
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from zulipterminal.ui_tools.buttons import MenuButton
from zulipterminal.config import is_command_key


class WriteBox(urwid.Pile):
    def __init__(self, view: Any) -> None:
        super(WriteBox, self).__init__(self.main_view(True))
        self.client = view.client
        self.view = view

    def main_view(self, new: bool) -> Any:
        if new:
            return []
        else:
            self.contents.clear()

    def set_editor_mode(self) -> None:
        # if not in the editor mode already set editor_mode to True.
        if not self.view.controller.editor_mode:
            self.view.controller.editor_mode = True
            self.view.controller.editor = self

    def private_box_view(self, button: Any=None, email: str='') -> None:
        self.set_editor_mode()
        if email == '' and button is not None:
            email = button.email
        self.to_write_box = ReadlineEdit(u"To: ", edit_text=email)
        self.msg_write_box = ReadlineEdit(multiline=True)
        to_write_box = urwid.LineBox(
            self.to_write_box, tlcorner=u'─', tline=u'─', lline=u'',
            trcorner=u'─', blcorner=u'─', rline=u'',
            bline=u'─', brcorner=u'─'
        )
        self.contents = [
            (to_write_box, self.options()),
            (self.msg_write_box, self.options()),
        ]
        self.focus_position = 1

    def stream_box_view(self, button: Any=None, caption: str='',
                        title: str='') -> None:
        self.set_editor_mode()
        self.to_write_box = None
        if caption == '' and button is not None:
            caption = button.caption
        self.msg_write_box = ReadlineEdit(multiline=True)
        self.stream_write_box = ReadlineEdit(
            caption=u"Stream:  ",
            edit_text=caption
        )
        self.title_write_box = ReadlineEdit(caption=u"Title:  ",
                                            edit_text=title)

        header_write_box = urwid.Columns([
            urwid.LineBox(
                self.stream_write_box, tlcorner=u'─', tline=u'─', lline=u'',
                trcorner=u'┐', blcorner=u'─', rline=u'│',
                bline=u'─', brcorner=u'┘'
            ),
            urwid.LineBox(
                self.title_write_box, tlcorner=u'─', tline=u'─', lline=u'',
                trcorner=u'─', blcorner=u'─', rline=u'',
                bline=u'─', brcorner=u'─'
            ),
        ])
        write_box = [
            (header_write_box, self.options()),
            (self.msg_write_box, self.options()),
        ]
        self.contents = write_box

    def keypress(self, size: Tuple[int, int], key: str) -> str:
        if is_command_key('SEND_MESSAGE', key):
            if not self.to_write_box:
                request = {
                    'type': 'stream',
                    'to': self.stream_write_box.edit_text,
                    'subject': self.title_write_box.edit_text,
                    'content': self.msg_write_box.edit_text,
                }
                response = self.client.send_message(request)
            else:
                request = {
                    'type': 'private',
                    'to': self.to_write_box.edit_text,
                    'content': self.msg_write_box.edit_text,
                }
                response = self.client.send_message(request)
            if response['result'] == 'success':
                self.msg_write_box.edit_text = ''
        elif is_command_key('GO_BACK', key):
            self.view.controller.editor_mode = False
            self.main_view(False)
            self.view.middle_column.set_focus('body')
        elif is_command_key('TAB', key):
            if len(self.contents) == 0:
                return key
            # toggle focus position
            if self.focus_position == 0 and self.to_write_box is None:
                if self.contents[0][0].focus_col == 0:
                    self.contents[0][0].focus_col = 1
                    return key
                else:
                    self.contents[0][0].focus_col = 0
            self.focus_position = self.focus_position == 0
            self.contents[0][0].focus_col = 0

        key = super(WriteBox, self).keypress(size, key)
        return key


class MessageBox(urwid.Pile):
    def __init__(self, message: Dict[str, Any], model: Any,
                 last_message: Any) -> None:
        self.model = model
        self.message = message
        self.caption = ''
        self.stream_id = None  # type: Union[int, None]
        self.title = ''
        self.email = ''
        self.last_message = last_message
        # if this is the first message
        if self.last_message is None:
            self.last_message = defaultdict(dict)
        super(MessageBox, self).__init__(self.main_view())

    def _time_for_message(self, message: Dict[str, Any]) -> str:
        return ctime(message['timestamp'])[:-8]

    def stream_view(self) -> Any:
        self.caption = self.message['display_recipient']
        self.stream_id = self.message['stream_id']
        self.title = self.message['subject']
        # If the topic of last message is same
        # as current message
        if (self.last_message['type'] == 'stream' and
                self.title == self.last_message['subject'] and
                self.caption == self.last_message['display_recipient']):
            return None
        bar_color = self.model.stream_dict[self.stream_id]['color']
        bar_color = 's' + bar_color[:2] + bar_color[3] + bar_color[5]
        stream_title_markup = ('bar', [
            (bar_color, '{} >'.format(self.caption)),
            ('title', ' {} '.format(self.title))
        ])
        stream_title = urwid.Text(stream_title_markup)
        header = urwid.AttrWrap(stream_title, 'bar')
        header.markup = stream_title_markup
        return header

    def private_view(self) -> Any:
        self.email = self.message['sender_email']
        self.user_id = self.message['sender_id']

        recipient_ids = [{recipient['id']
                          for recipient in message['display_recipient']
                          if 'id' in recipient}
                         for message in (self.message, self.last_message)
                         if 'display_recipient' in message]
        if len(recipient_ids) == 2 and\
                recipient_ids[0] == recipient_ids[1] and\
                self.last_message['type'] == 'private':
            return None
        self.recipients = ', '.join(list(
            recipient['full_name']
            for recipient in self.message['display_recipient']
            if recipient['email'] != self.model.client.email
        ))
        title_markup = ('header', [
            ('custom', 'Private Messages with'),
            ('selected', ": "),
            ('custom', self.recipients)
        ])
        title = urwid.Text(title_markup)
        header = urwid.AttrWrap(title, 'bar')
        header.markup = title_markup
        return header

    def reactions_view(self, reactions: List[Dict[str, Any]]) -> Any:
        if not reactions:
            return ''
        try:
            reacts = defaultdict(int)  # type: Dict[str, int]
            custom_reacts = defaultdict(int)  # type: Dict[str, int]
            for reaction in reactions:
                if reaction['reaction_type'] == 'unicode_emoji':
                    reacts[reaction['emoji_code']] += 1
                elif reaction['reaction_type'] == 'realm_emoji':
                    custom_reacts[reaction['emoji_name']] += 1
            dis = [
                '\\U' + '0'*(8-len(emoji)) + emoji + ' ' + str(reacts[emoji]) +
                ' ' for emoji in reacts]
            emojis = ''.join(e.encode().decode('unicode-escape') for e in dis)
            custom_emojis = ''.join(
                ['{} {}'.format(r, custom_reacts[r]) for r in custom_reacts])
            return urwid.Padding(
                urwid.Text(([
                    ('emoji', emoji.demojize(emojis + custom_emojis))
                ])), align='left', width=('relative', 90), left=25,
                min_width=50)
        except Exception:
            return ''

    def soup2markup(self, soup: Any) -> List[Any]:
        # Ensure a string is provided, in case the soup finds none
        # This could occur if eg. an image is removed or not shown
        markup = ['']
        for element in soup:
            if isinstance(element, NavigableString):
                # NORMAL STRINGS
                markup.append(element)
            elif element.name == 'div' and element.attrs and\
                    'message_embed' in element.attrs.get('class'):
                # Do not display embedded content
                # since Embedded content can be very dynamic
                # TODO: Support Embedded content
                continue
            elif element.name == 'span' and element.attrs and\
                    'user-mention' in element.attrs.get('class', []):
                # USER MENTIONS
                markup.append(('span', element.text))
            elif element.name == 'a':
                # LINKS
                link = element.attrs['href']
                text = element.text
                if link == text:
                    # If the link and text are same
                    # usually the case when user just pastes
                    # a link then just display the link
                    markup.append(text)
                else:
                    if link.startswith('/user_uploads/'):
                        # Append org url to before user_uploads to convert it
                        # into a link.
                        link = self.model.client.base_url + link
                    markup.append(
                        ('link', '[' + text + ']' + '(' + link + ')'))
            elif element.name == 'blockquote':
                # BLOCKQUOTE TEXT
                markup.append((
                    'blockquote', self.soup2markup(element)
                ))
            elif element.name == 'code':
                markup.append((
                    'code', element.text
                ))
            elif element.name == 'div' and element.attrs and\
                    'codehilite' in element.attrs.get('class', []):
                markup.append((
                    'code', element.text
                ))
            elif element.name == 'strong':
                    markup.append(('bold', element.text))
            elif element.name == 'ul':
                # TODO: Support nested lists.
                markup.append(element.text)
            else:
                markup.extend(self.soup2markup(element))
        return markup

    def main_view(self) -> List[Any]:
        if self.message['type'] == 'stream':
            header = self.stream_view()
        else:
            header = self.private_view()

        reactions = self.reactions_view(self.message['reactions'])
        soup = BeautifulSoup(self.message['content'], 'lxml')
        content = (None, self.soup2markup(soup))
        content = urwid.Padding(urwid.Text(content),
                                align='left', width=('relative', 90), left=25,
                                min_width=50)

        message_is_starred = 'starred' in self.message['flags']
        message_author = self.message['sender_full_name']
        message_time = self._time_for_message(self.message)

        # Statements as to how the message varies from the previous one
        different_topic = header is not None
        different_author = (
            self.last_message['sender_full_name'] != message_author)
        more_than_24h_apart = (
            'timestamp' in self.last_message and
            (datetime.fromtimestamp(self.message['timestamp']) -
             datetime.fromtimestamp(self.last_message['timestamp'])).days)
        different_timestamp = (
            'timestamp' in self.last_message and
            message_time != self._time_for_message(self.last_message))
        different_star_status = (
            message_is_starred != ('starred' in self.last_message['flags']))
        no_differences = (not different_topic and
                          not different_author and
                          not more_than_24h_apart and
                          not different_timestamp and
                          not different_star_status)

        # Include author name/star/time under various conditions
        TextType = Dict[str, Tuple[Optional[str], str]]
        text = {key: (None, ' ')
                for key in ('author', 'star', 'time')}  # type: TextType
        if different_topic or different_author or more_than_24h_apart:
            text['author'] = ('name', message_author)
        if message_is_starred:
            text['star'] = ('starred', "*")
        if different_topic or different_author or different_timestamp:
            text['time'] = ('time', message_time)

        content_header = urwid.Columns([
            ('weight', 10, urwid.Text(text['author'])),
            (1, urwid.Text(text['star'], align='right')),
            (16, urwid.Text(text['time'], align='right')),
            ], dividechars=1)

        view = [header, content_header, content, reactions]
        if header is None:
            view.remove(header)
        if no_differences:
            view.remove(content_header)
        if reactions == '':
            view.remove(reactions)
        return view

    def selectable(self) -> bool:
        return True

    def mouse_event(self, size: Tuple[int, int], event: Any, button: Any,
                    col: int, row: int, focus: int) -> Union[bool, Any]:
        if event == 'mouse press':
            if button == 1:
                self.keypress(size, 'enter')
                return True
        return super(MessageBox, self).mouse_event(size, event, button, col,
                                                   row, focus)

    def get_recipients(self) -> str:
        emails = []
        for recipient in self.message['display_recipient']:
            email = recipient['email']
            if email == self.model.client.email:
                continue
            emails.append(recipient['email'])
        return ', '.join(emails)

    def keypress(self, size: Tuple[int, int], key: str) -> str:
        if is_command_key('ENTER', key):
            if self.message['type'] == 'private':
                self.model.controller.view.write_box.private_box_view(
                    email=self.get_recipients()
                )
            elif self.message['type'] == 'stream':
                self.model.controller.view.write_box.stream_box_view(
                    caption=self.message['display_recipient'],
                    title=self.message['subject']
                )
        elif is_command_key('STREAM_MESSAGE', key):
            if self.message['type'] == 'private':
                self.model.controller.view.write_box.private_box_view(
                    email=self.get_recipients()
                )
            elif self.message['type'] == 'stream':
                self.model.controller.view.write_box.stream_box_view(
                    caption=self.message['display_recipient']
                )
        elif is_command_key('STREAM_NARROW', key):
            if self.message['type'] == 'private':
                self.model.controller.narrow_to_user(self)
            elif self.message['type'] == 'stream':
                self.model.controller.narrow_to_stream(self)
        elif is_command_key('TOPIC_NARROW', key):
            if self.message['type'] == 'private':
                self.model.controller.narrow_to_user(self)
            elif self.message['type'] == 'stream':
                self.model.controller.narrow_to_topic(self)
        elif is_command_key('GO_BACK', key):
            self.model.controller.show_all_messages(self)
        elif is_command_key('REPLY_AUTHOR', key):
            self.model.controller.view.write_box.private_box_view(
                email=self.message['sender_email']
            )
        elif is_command_key('ALL_PM', key):
            self.model.controller.show_all_pm(self)
        elif is_command_key('MENTION_REPLY', key):
            self.keypress(size, 'enter')
            mention = '@**' + self.message['sender_full_name'] + '** '
            self.model.controller.view.write_box.msg_write_box.set_edit_text(
                mention)
            self.model.controller.view.write_box.msg_write_box.set_edit_pos(
                len(mention))
            self.model.controller.view.middle_column.set_focus('footer')
        elif is_command_key('QUOTE_REPLY', key):
            self.keypress(size, 'enter')
            quote = '```quote\n' + self.message['content'] + '\n```\n'
            self.model.controller.view.write_box.msg_write_box.set_edit_text(
                quote)
            self.model.controller.view.write_box.msg_write_box.set_edit_pos(
                len(quote))
            self.model.controller.view.middle_column.set_focus('footer')
        return key


class SearchBox(urwid.Pile):
    def __init__(self, controller: Any) -> None:
        self.controller = controller
        super(SearchBox, self).__init__(self.main_view())

    def main_view(self) -> Any:
        self.text_box = ReadlineEdit(u"Search: ")
        # Add some text so that when packing,
        # urwid doesn't hide the widget.
        self.msg_narrow = urwid.Text("DONT HIDE")
        w = urwid.Columns([
            ('pack', self.msg_narrow),
            ('pack', urwid.Text("  ")),
            self.text_box,
        ])
        self.w = urwid.LineBox(
            w, tlcorner=u'', tline=u'', lline=u'',
            trcorner=u'', blcorner=u'─', rline=u'',
            bline=u'─', brcorner=u'─')
        return [self.w]

    def keypress(self, size: Tuple[int, int], key: str) -> str:
        if is_command_key('GO_BACK', key):
            self.text_box.set_edit_text("")
            self.controller.editor_mode = False
            self.controller.view.middle_column.set_focus('body')
            return key

        elif is_command_key('ENTER', key):
            self.controller.editor_mode = False
            self.controller.model.index['search'] = set()
            self.controller.search_messages(self.text_box.edit_text)
            self.controller.view.middle_column.set_focus('body')
            return key

        key = super(SearchBox, self).keypress(size, key)
        return key


class UserSearchBox(urwid.Edit):
    """
    Search Box to search users in real-time.
    """

    def __init__(self, user_view: Any) -> None:
        self.user_view = user_view
        super(UserSearchBox, self).__init__(edit_text="Search people")

    def keypress(self, size: Tuple[int, int], key: str) -> str:
        if is_command_key('ENTER', key):
            self.user_view.view.controller.editor_mode = False
            self.user_view.set_focus("body")
        if is_command_key('GO_BACK', key):
            self.user_view.view.controller.editor_mode = False
            self.set_edit_text("Search people")
            self.user_view.set_focus("body")
            self.user_view.keypress(size, 'esc')

        return super(UserSearchBox, self).keypress(size, key)


class StreamSearchBox(urwid.Edit):
    """
    Search Box to search streams in real-time.urwid
    """

    def __init__(self, stream_view: Any) -> None:
        self.stream_view = stream_view
        super(StreamSearchBox, self).__init__(edit_text="Search streams")

    def keypress(self, size: Tuple[int, int], key: str) -> str:
        if is_command_key('ENTER', key):
            self.stream_view.view.controller.editor_mode = False
            self.stream_view.set_focus("body")
            self.stream_view.body.set_focus(0)
        if is_command_key('GO_BACK', key):
            self.stream_view.view.controller.editor_mode = False
            self.set_edit_text("Search streams")
            self.stream_view.set_focus("body")
            self.stream_view.keypress(size, 'esc')

        return super(StreamSearchBox, self).keypress(size, key)
