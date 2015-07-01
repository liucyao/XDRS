import copy
import gettext
import locale
import os
import re

from babel import localedata
import six

_localedir = os.environ.get('xdrs'.upper() + '_LOCALEDIR')

_t = gettext.translation('xdrs', localedir=_localedir, fallback=True)

# We use separate translation catalogs for each log level, so set up a
# mapping between the log level name and the translator. The domain
# for the log level is project_name + "-log-" + log_level so messages
# for each level end up in their own catalog.
_t_log_levels = dict(
    (level, gettext.translation('xdrs' + '-log-' + level,
                                localedir=_localedir,
                                fallback=True))
    for level in ['info', 'warning', 'error', 'critical']
)

_AVAILABLE_LANGUAGES = {}

USE_LAZY = False

def enable_lazy():
    """
    Convenience function for configuring _() to use lazy gettext

    Call this at the start of execution to enable the gettextutils._
    function to use lazy gettext functionality. This is useful if
    your project is importing _ directly instead of using the
    gettextutils.install() way of importing the _ function.
    """
    global USE_LAZY
    USE_LAZY = True


def _(msg):
    if USE_LAZY:
        return Message(msg, domain='xdrs')
    else:
        if six.PY3:
            return _t.gettext(msg)
        return _t.ugettext(msg)

class Message(six.text_type):
    """
    A Message object is a unicode object that can be translated.
    Translation of Message is done explicitly using the translate() method.
    For all non-translation intents and purposes, a Message is simply unicode,
    and can be treated as such.
    """

    def __new__(cls, msgid, msgtext=None, params=None,
                domain='xdrs', *args):
        """
        Create a new Message object.

        In order for translation to work gettext requires a message ID, this
        msgid will be used as the base unicode text. It is also possible
        for the msgid and the base unicode text to be different by passing
        the msgtext parameter.
        """
        # If the base msgtext is not given, we use the default translation
        # of the msgid (which is in English) just in case the system locale is
        # not English, so that the base text will be in that locale by default.
        if not msgtext:
            msgtext = Message._translate_msgid(msgid, domain)
        # We want to initialize the parent unicode with the actual object that
        # would have been plain unicode if 'Message' was not enabled.
        msg = super(Message, cls).__new__(cls, msgtext)
        msg.msgid = msgid
        msg.domain = domain
        msg.params = params
        return msg

    def translate(self, desired_locale=None):
        """Translate this message to the desired locale.

        :param desired_locale: The desired locale to translate the message to,
                               if no locale is provided the message will be
                               translated to the system's default locale.

        :returns: the translated message in unicode
        """

        translated_message = Message._translate_msgid(self.msgid,
                                                      self.domain,
                                                      desired_locale)
        if self.params is None:
            # No need for more translation
            return translated_message

        # This Message object may have been formatted with one or more
        # Message objects as substitution arguments, given either as a single
        # argument, part of a tuple, or as one or more values in a dictionary.
        # When translating this Message we need to translate those Messages too
        translated_params = _translate_args(self.params, desired_locale)

        translated_message = translated_message % translated_params

        return translated_message

    @staticmethod
    def _translate_msgid(msgid, domain, desired_locale=None):
        if not desired_locale:
            system_locale = locale.getdefaultlocale()
            # If the system locale is not available to the runtime use English
            if not system_locale[0]:
                desired_locale = 'en_US'
            else:
                desired_locale = system_locale[0]

        locale_dir = os.environ.get(domain.upper() + '_LOCALEDIR')
        lang = gettext.translation(domain,
                                   localedir=locale_dir,
                                   languages=[desired_locale],
                                   fallback=True)
        if six.PY3:
            translator = lang.gettext
        else:
            translator = lang.ugettext

        translated_message = translator(msgid)
        return translated_message

    def __mod__(self, other):
        # When we mod a Message we want the actual operation to be performed
        # by the parent class (i.e. unicode()), the only thing  we do here is
        # save the original msgid and the parameters in case of a translation
        params = self._sanitize_mod_params(other)
        unicode_mod = super(Message, self).__mod__(params)
        modded = Message(self.msgid,
                         msgtext=unicode_mod,
                         params=params,
                         domain=self.domain)
        return modded

    def _sanitize_mod_params(self, other):
        """Sanitize the object being modded with this Message.

        - Add support for modding 'None' so translation supports it
        - Trim the modded object, which can be a large dictionary, to only
        those keys that would actually be used in a translation
        - Snapshot the object being modded, in case the message is
        translated, it will be used as it was when the Message was created
        """
        if other is None:
            params = (other,)
        elif isinstance(other, dict):
            params = self._trim_dictionary_parameters(other)
        else:
            params = self._copy_param(other)
        return params

    def _trim_dictionary_parameters(self, dict_param):
        """Return a dict that only has matching entries in the msgid."""
        # NOTE(luisg): Here we trim down the dictionary passed as parameters
        # to avoid carrying a lot of unnecessary weight around in the message
        # object, for example if someone passes in Message() % locals() but
        # only some params are used, and additionally we prevent errors for
        # non-deepcopyable objects by unicoding() them.

        # Look for %(param) keys in msgid;
        # Skip %% and deal with the case where % is first character on the line
        keys = re.findall('(?:[^%]|^)?%\((\w*)\)[a-z]', self.msgid)

        # If we don't find any %(param) keys but have a %s
        if not keys and re.findall('(?:[^%]|^)%[a-z]', self.msgid):
            # Apparently the full dictionary is the parameter
            params = self._copy_param(dict_param)
        else:
            params = {}
            # Save our existing parameters as defaults to protect
            # ourselves from losing values if we are called through an
            # (erroneous) chain that builds a valid Message with
            # arguments, and then does something like "msg % kwds"
            # where kwds is an empty dictionary.
            src = {}
            if isinstance(self.params, dict):
                src.update(self.params)
            src.update(dict_param)
            for key in keys:
                params[key] = self._copy_param(src[key])

        return params

    def _copy_param(self, param):
        try:
            return copy.deepcopy(param)
        except TypeError:
            # Fallback to casting to unicode this will handle the
            # python code-like objects that can't be deep-copied
            return six.text_type(param)

    def __add__(self, other):
        msg = _('Message objects do not support addition.')
        raise TypeError(msg)

    def __radd__(self, other):
        return self.__add__(other)

    def __str__(self):
        # NOTE(luisg): Logging in python 2.6 tries to str() log records,
        # and it expects specifically a UnicodeError in order to proceed.
        msg = _('Message objects do not support str() because they may '
                'contain non-ascii characters. '
                'Please use unicode() or translate() instead.')
        raise UnicodeError(msg)


def get_available_languages(domain):
    """
    Lists the available languages for the given translation domain.
    """
    if domain in _AVAILABLE_LANGUAGES:
        return copy.copy(_AVAILABLE_LANGUAGES[domain])

    localedir = '%s_LOCALEDIR' % domain.upper()
    find = lambda x: gettext.find(domain,
                                  localedir=os.environ.get(localedir),
                                  languages=[x])

    # NOTE(mrodden): en_US should always be available (and first in case
    # order matters) since our in-line message strings are en_US
    language_list = ['en_US']
    # NOTE(luisg): Babel <1.0 used a function called list(), which was
    # renamed to locale_identifiers() in >=1.0, the requirements master list
    # requires >=0.9.6, uncapped, so defensively work with both. We can remove
    # this check when the master list updates to >=1.0, and update all projects
    list_identifiers = (getattr(localedata, 'list', None) or
                        getattr(localedata, 'locale_identifiers'))
    locale_identifiers = list_identifiers()

    for i in locale_identifiers:
        if find(i) is not None:
            language_list.append(i)

    # NOTE(luisg): Babel>=1.0,<1.3 has a bug where some OpenStack supported
    # locales (e.g. 'zh_CN', and 'zh_TW') aren't supported even though they
    # are perfectly legitimate locales:
    #     https://github.com/mitsuhiko/babel/issues/37
    # In Babel 1.3 they fixed the bug and they support these locales, but
    # they are still not explicitly "listed" by locale_identifiers().
    # That is  why we add the locales here explicitly if necessary so that
    # they are listed as supported.
    aliases = {'zh': 'zh_CN',
               'zh_Hant_HK': 'zh_HK',
               'zh_Hant': 'zh_TW',
               'fil': 'tl_PH'}
    for (locale, alias) in six.iteritems(aliases):
        if locale in language_list and alias not in language_list:
            language_list.append(alias)

    _AVAILABLE_LANGUAGES[domain] = language_list
    return copy.copy(language_list)


def translate(obj, desired_locale=None):
    """
    Gets the translated unicode representation of the given object.

    If the object is not translatable it is returned as-is.
    If the locale is None the object is translated to the system locale.

    :param obj: the object to translate
    :param desired_locale: the locale to translate the message to, if None the
                           default system locale will be used
    :returns: the translated object in unicode, or the original object if
              it could not be translated
    """
    message = obj
    if not isinstance(message, Message):
        # If the object to translate is not already translatable,
        # let's first get its unicode representation
        message = six.text_type(obj)
    if isinstance(message, Message):
        # Even after unicoding() we still need to check if we are
        # running with translatable unicode before translating
        return message.translate(desired_locale)
    return obj


def _translate_args(args, desired_locale=None):
    """Translates all the translatable elements of the given arguments object.

    This method is used for translating the translatable values in method
    arguments which include values of tuples or dictionaries.
    If the object is not a tuple or a dictionary the object itself is
    translated if it is translatable.

    If the locale is None the object is translated to the system locale.

    :param args: the args to translate
    :param desired_locale: the locale to translate the args to, if None the
                           default system locale will be used
    :returns: a new args object with the translated contents of the original
    """
    if isinstance(args, tuple):
        return tuple(translate(v, desired_locale) for v in args)
    if isinstance(args, dict):
        translated_dict = {}
        for (k, v) in six.iteritems(args):
            translated_v = translate(v, desired_locale)
            translated_dict[k] = translated_v
        return translated_dict
    return translate(args, desired_locale)