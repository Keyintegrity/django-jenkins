import os
import sys
import time
import traceback
from unittest import TextTestResult
from unittest.result import STDOUT_LINE, STDERR_LINE

from xml.etree import ElementTree as ET

from django.test.runner import DiscoverRunner
from django.utils.encoding import smart_text


class EXMLTestResult(TextTestResult):
    def __init__(self, *args, **kwargs):
        self.case_start_time = time.time()
        self.run_start_time = None
        self.tree = None
        super(EXMLTestResult, self).__init__(*args, **kwargs)

    def startTest(self, test):
        self.case_start_time = time.time()
        super(EXMLTestResult, self).startTest(test)

    def startTestRun(self):
        self.tree = ET.Element('testsuite')
        self.run_start_time = time.time()
        super(EXMLTestResult, self).startTestRun()

    def addSuccess(self, test):
        self.testcase = self._make_testcase_element(test)
        super(EXMLTestResult, self).addSuccess(test)

    def addFailure(self, test, err):
        self.testcase = self._make_testcase_element(test)
        test_result = ET.SubElement(self.testcase, 'failure')
        self._add_tb_to_test(test, test_result, err)
        super(EXMLTestResult, self).addFailure(test, err)

    def addError(self, test, err):
        self.testcase = self._make_testcase_element(test)
        test_result = ET.SubElement(self.testcase, 'error')
        self._add_tb_to_test(test, test_result, err)
        super(EXMLTestResult, self).addError(test, err)

    def addUnexpectedSuccess(self, test):
        self.testcase = self._make_testcase_element(test)
        test_result = ET.SubElement(self.testcase, 'skipped')
        test_result.set('message', 'Test Skipped: Unexpected Success')
        super(EXMLTestResult, self).addUnexpectedSuccess(test)

    def addSkip(self, test, reason):
        self.testcase = self._make_testcase_element(test)
        test_result = ET.SubElement(self.testcase, 'skipped')
        test_result.set('message', 'Test Skipped: %s' % reason)
        super(EXMLTestResult, self).addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.testcase = self._make_testcase_element(test)
        test_result = ET.SubElement(self.testcase, 'skipped')
        self._add_tb_to_test(test, test_result, err)
        super(EXMLTestResult, self).addExpectedFailure(test, err)

    def stopTest(self, test):
        if self.buffer:
            output = sys.stdout.getvalue() if hasattr(sys.stdout, 'getvalue') else ''
            if output:
                sysout = ET.SubElement(self.testcase, 'system-out')
                sysout.text = smart_text(output, errors='ignore')

            error = sys.stderr.getvalue() if hasattr(sys.stderr, 'getvalue') else ''
            if error:
                syserr = ET.SubElement(self.testcase, 'system-err')
                syserr.text = smart_text(error, errors='ignore')

        super(EXMLTestResult, self).stopTest(test)

    def stopTestRun(self):
        run_time_taken = time.time() - self.run_start_time
        self.tree.set('name', 'Django Project Tests')
        self.tree.set('errors', str(len(self.errors)))
        self.tree.set('failures', str(len(self.failures)))
        self.tree.set('skips', str(len(self.skipped)))
        self.tree.set('tests', str(self.testsRun))
        self.tree.set('time', "%.3f" % run_time_taken)
        super(EXMLTestResult, self).stopTestRun()

    def _make_testcase_element(self, test):
        time_taken = time.time() - self.case_start_time
        classname = ('%s.%s' % (test.__module__, test.__class__.__name__)).split('.')
        testcase = ET.SubElement(self.tree, 'testcase')
        testcase.set('time', "%.6f" % time_taken)
        testcase.set('classname', '.'.join(classname))
        testcase.set('name', getattr(test, '_testMethodName',
                                     getattr(test, 'description', 'UNKNOWN')))
        return testcase

    def _restoreStdout(self):
        '''Disables buffering once the stdout/stderr are reset.'''
        super(EXMLTestResult, self)._restoreStdout()
        self.buffer = False

    def _add_tb_to_test(self, test, test_result, err):
        '''Add a traceback to the test result element'''
        exc_class, exc_value, tb = err
        tb_str = self._exc_info_to_string(err, test)
        test_result.set('type', '%s.%s' % (exc_class.__module__, exc_class.__name__))
        test_result.set('message', smart_text(exc_value))
        test_result.text = smart_text(tb_str)

    def _exc_info_to_string(self, err, test):
        """Converts a sys.exc_info()-style tuple of values into a string."""
        exctype, value, tb = err
        # Skip test runner traceback levels
        while tb and self._is_relevant_tb_level(tb):
            tb = tb.tb_next

        if exctype is test.failureException:
            # Skip assert*() traceback levels
            length = self._count_relevant_tb_levels(tb)
        else:
            length = None

        tb_e = traceback.TracebackException(
            exctype, value, tb, limit=length, capture_locals=self.tb_locals
        )
        msg_lines = list(tb_e.format())

        if self.buffer:
            # When running tests in parallel mode, sys.stdout and sys.stderr
            # may not be substituted with StringIO at this point. We need to
            # check for that.
            output = sys.stdout.getvalue() if hasattr(sys.stdout, 'getvalue') else ''
            error = sys.stderr.getvalue() if hasattr(sys.stderr, 'getvalue') else ''

            if output:
                if not output.endswith('\n'):
                    output += '\n'
                msg_lines.append(STDOUT_LINE % output)

            if error:
                if not error.endswith('\n'):
                    error += '\n'
                msg_lines.append(STDERR_LINE % error)

        return ''.join(msg_lines)

    def dump_xml(self, output_dir):
        """
        Dumps test result to xml
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        output = ET.ElementTree(self.tree)
        output.write(os.path.join(output_dir, 'junit.xml'), encoding="utf-8")


class CITestSuiteRunner(DiscoverRunner):
    def __init__(self, output_dir='reports', debug=False, **kwargs):
        self.output_dir = output_dir
        self.debug = debug
        super(CITestSuiteRunner, self).__init__(**kwargs)

    def run_suite(self, suite, **kwargs):
        result = self.test_runner(
            verbosity=self.verbosity,
            failfast=self.failfast,
            resultclass=EXMLTestResult,
            buffer=not self.debug
        ).run(suite)

        result.dump_xml(self.output_dir)

        return result
