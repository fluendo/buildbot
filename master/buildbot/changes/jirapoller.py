from datetime import datetime, timedelta

from twisted.internet import defer

from buildbot.changes import base
from buildbot.util.logger import Logger
from buildbot.util.state import StateMixin
from buildbot.util import httpclientservice
from buildbot.util import datetime2epoch
from buildbot.util import ascii2unicode

try:
    from jira import JIRA
except ImportError:
    JIRA = None

log = Logger()

def dt_parse(t):
    ret = datetime.strptime(t[0:16],'%Y-%m-%dT%H:%M')
    if t[17]=='+':
       ret-=timedelta(hours=int(t[18:20]),minutes=int(t[20:]))
    elif t[17]=='-':
       ret+=timedelta(hours=int(t[18:20]),minutes=int(t[20:]))
    return ret


class JiraIssuePoller(base.ReconfigurablePollingChangeSource,
                              StateMixin):
    compare_attrs = ("user", "token", "domain", "jql", "pollInterval",
                     "category", "pollAtLaunch", "name")
    db_class_name = 'JiraIssuePoller'

    def __init__(self, user, token, domain, jql, **kwargs):
        name = kwargs.get("name")
        if not name:
            kwargs["name"] = "JiraIssuePoller:" + domain + "/" + user + "/" + jql
        super(JiraIssuePoller, self).__init__(user, token, domain, jql, **kwargs)

    def checkConfig(self,
                    user,
                    token,
                    domain,
                    jql,
                    **kwargs):
        if not JIRA:
            config.error("The python module 'jira' is needed to use a JIRA "
                         "ChangeSource")
        base.ReconfigurablePollingChangeSource.checkConfig(
            self, name=self.name, **kwargs)

    def reconfigService(self,
                        user,
                        token,
                        domain,
                        jql,
                        pollInterval=10,
                        pollAtLaunch=True,
                        category=None,
                        **kwargs):
        # Keep the configuration
        self.token = token
        self.user = user
        self.domain = domain
        self.jql = jql
        self.pollInterval = pollInterval
        self.pollAtLaunch = pollAtLaunch
        # Create our connection to JIRA
        base_url = 'https://' + domain + '.atlassian.net'
        self.jira = JIRA(base_url, basic_auth=(user, token))
        self.category = category if callable(category) else ascii2unicode(
            category)


    @defer.inlineCallbacks
    def poll(self):
        log.debug("JQL {0}".format(self.jql))
        # get every issue with the provided JQL
        issues = self.jira.search_issues(self.jql, expand='changelog')
        for i in issues:
            # Get the changelog
            changelog = i.changelog
            for history in changelog.histories:
                try:
                    author=history.historyMetadata.actor.id
                except AttributeError:
                    author=history.author.key

                created = dt_parse(history.created)
                # Emit the change
                log.debug("Changes for {0}".format(i.key))
                yield self.master.data.updates.addChange(
                    author=author,
                    revision=history.created,
                    comments=u'JIRA issue {0} changelog'.format(i.key),
                    when_timestamp=datetime2epoch(created),
                    branch='master',
                    category=self.category,
                    project=i.fields.project.name,
                    repository=self.domain)
