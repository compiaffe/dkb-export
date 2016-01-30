#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# DKB transaction CSV exporter
# Copyright (C) 2015 Tom Fischer (https://plus.google.com/+TomFischer0810)
#
# Inspired by Christian Hoffmann <mail@hoffmann-christian.info>,
# see https://github.com/hoffie/dkb-visa,
# but extended to fetch also bank account transactions. You still need to
# have dkb.py module in the same directory as dkbweb.py.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import dkb
import re
import sys
import logging
from bs4 import BeautifulSoup
#from mechanize import Browser
from datetime import date
from datetime import datetime
import time
#import codecs
import os

DEBUG = False

logger = logging.getLogger(__name__)

class DkbScraper(dkb.DkbScraper):
    LOGOUTURL = "https://banking.dkb.de/dkb/-?$part=DkbTransactionBanking.infobar.logout-button&$event=logout"

    def bank_account_transactions_overview(self):
        """
        Navigates the internal browser state to the bank account
        transaction overview menu
        """
        logger.info("Navigating to 'Kontoumsätze'...")
        br = self.br
        BeautifulSoup(br.response().read(), "html.parser")
        for link in br.links():
            if re.search("Kontoums.*tze", link.text, re.I):
                br.follow_link(link)
                return
            if 'weitergeleitet' in link.text:
                br.follow_link(link)
            if link.text == 'here':
                br.follow_link(text="here")
        raise RuntimeError("Unable to find link 'Kontoumsätze' -- "
            "Maybe the login went wrong?")

    def _get_transaction_selection_form_ba(self):
        """
        Internal.

        Returns the transaction selection form object (mechanize)
        """
        for form in self.br.forms():
            try:
                form.find_control(name="slBankAccount", type="select")
                return form
            except Exception:
                continue

        raise RuntimeError("Unable to find transaction selection form")

    def _select_all_transactions_from_ba(self, form, from_date, to_date):
        """
        Internal.

        Checks the radio box "Zeitraum: vom" and populates the
        "from" and "to" with the given values.

        @param mechanize.HTMLForm form
        @param str from_date dd.mm.YYYY
        @param str to_date dd.mm.YYYY
        """
        try:
            radio_ctrl = form.find_control("searchPeriodRadio")
        except Exception:
            raise RuntimeError("Unable to find search period radio box")

        all_transactions_item = None
        for item in radio_ctrl.items:
            if item.id.endswith(":1"):
                all_transactions_item = item
                break

        if not all_transactions_item:
            raise RuntimeError(
                "Unable to find 'Zeitraum: vom' radio box")

        form[radio_ctrl.name] = ["1"] # select from/to date, not "all"

        try:
            from_item = form.find_control(name="transactionDate")
        except Exception:
            raise RuntimeError("Unable to find 'vom' (from) date field")

        from_item.value = from_date

        try:
            to_item = form.find_control(name="toTransactionDate")
        except Exception:
            raise RuntimeError("Unable to find 'bis' (to) date field")

        to_item.value = to_date

    def _select_bank_account(self, form, baid):
        """
        Internal.

        Selects the correct bank account from the dropdown menu in the
        transaction selection form.

        @param mechanize.HTMLForm form
        @param str baid: full bank account number
        """
        try:
            ba_list = form.find_control("slBankAccount", type="select")
        except Exception:
            raise RuntimeError("Unable to find bank account selection form")

        for item in ba_list.get_items():
            # find right bank account...
            for label in item.get_labels():
                ls = label.text.split("/") # I don't know if it's better to extract the bank account number using regex
                if len(ls) > 2:
                    acc = ls[1].strip().split()[-1]
                    if ((len(baid) == 4) and (baid == acc[-4:])) or (baid == acc):
                        form.set_value([item.name], name=ba_list.name, type="select")
                        return

        raise RuntimeError("Unable to find the right bank account")


    def select_transactions_ba(self, baid, from_date, to_date):
        """
        Changes the current view to show all transactions between
        from_date and to_date for the bank account identified by the
        given full bank account number.

        @param str baid: full bank account number
        @param str from_date dd.mm.YYYY
        @param str to_date dd.mm.YYYY
        """
        br = self.br
        logger.info("Selecting transactions in time frame %s - %s...",
            from_date, to_date)

        br.form = form = self._get_transaction_selection_form_ba()
        self._select_bank_account(form, baid)
        self._select_all_transactions_from_ba(form, from_date, to_date)
        br.submit()

    def logout(self):
        """
        Performs the logout process so that the session is closed on the DKB server.
        """
        self.br.open(self.LOGOUTURL)

def scrape_page():
    fetcher = DkbScraper()

    if DEBUG:
        logger = logging.getLogger("mechanize")
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.INFO)
        #fetcher.br.set_debug_http(True)
        fetcher.br.set_debug_responses(True)
        #fetcher.br.set_debug_redirects(True)

    fetcher.login(args.userid, pin)
    if args.baid:
        fetcher.bank_account_transactions_overview()
        fetcher.select_transactions_ba(args.baid, from_date, args.to_date)
    elif args.cardid:
        fetcher.credit_card_transactions_overview()
        fetcher.select_transactions(args.cardid, from_date, args.to_date)

    csv_text = fetcher.get_transaction_csv()
    # the logout should happen here
    fetcher.logout()
    return csv_text

if __name__ == '__main__':
    """
    Added a switch for bank account instead of credit card.  That makes
    `--cardid` optional but one of them must be given.
    """
    from getpass import getpass
    from argparse import ArgumentParser

    logging.basicConfig(level=logging.DEBUG)

    cli = ArgumentParser()
    cli.add_argument("--userid",
        help="Your user id (same as used for login)")
    cli.add_argument("--pin",
        help="Your user PIN (same as used for login). Use with care!")
    cli.add_argument("--baid",
        help="Full bank account number")
    cli.add_argument("--cardid",
        help="Last 4 digits of your card number")
    cli.add_argument("--input", "-i",
        help="Input path (CSV)")
    cli.add_argument("--output", "-o",
        help="Output path (QIF)")
    cli.add_argument("--qif-account",
        help="Default QIF account name (e.g. Aktiva:VISA)")
    cli.add_argument("--from-date",
        help="Export transactions as of... (DD.MM.YYYY)")
    cli.add_argument("--to-date",
        help="Export transactions until... (DD.MM.YYYY)",
        default=date.today().strftime('%d.%m.%Y'))
    cli.add_argument("--raw", action="store_true",
        help="Store the raw CSV file instead of QIF")

    args = cli.parse_args()
    if not args.userid:
        cli.error("Please specify a valid user id")
    if (not args.baid and not args.cardid) or (args.baid and args.cardid): # at least one must be given but both are not allowed
        cli.error("Please specify a valid bank account number _or_ card id")

    def is_valid_date(date):
        return date and bool(re.match('^\d{1,2}\.\d{1,2}\.\d{2,5}\Z', date))

    from_date = args.from_date
    if not args.from_date:
        # one year should be enough
        #from_date = (datetime.now() - relativedelta(years=1)).strftime("%d.%m.%Y")
        d = date.today()
        years = -1
        try:
            from_date = d.replace(year = d.year + years)
        except ValueError:
            from_date = d + (date(d.year + years, 1, 1) - date(d.year, 1, 1))
        from_date = from_date.strftime("%d.%m.%Y")
    if not args.to_date:
        to_date = time.strftime("%d.%m.%Y")
    while not is_valid_date(from_date):
        from_date = raw_input("Start time: ")
    if not is_valid_date(args.to_date):
        cli.error("Please specify a valid end time")
    if not args.output:
        cli.error("Please specify a valid output path")
    if args.input:
        logger.info("Won't fetch data. Just converting the csv-file")

    if args.pin:
        pin = args.pin
    else:
        pin = ""
        if os.isatty(0):
            while not pin.strip():
                pin = getpass('PIN: ')
        else:
            pin = sys.stdin.read().strip()

    # create a formatter to get the default output encoding
    dummyqif = dkb.DkbConverter("")

    if args.baid:
        start=7
    elif args.cardid:
        start=8

    if args.input:
        with open(args.input, 'r') as fh:
            logger.info("Reading from %s" % args.input)
            csv_text=fh.read()
            csv_text = csv_text.decode(dummyqif.OUTPUT_CHARSET)
    else:
        csv_text=scrape_page()
        csv_text = csv_text.decode(dummyqif.INPUT_CHARSET)

    # check that unparseable lines are not included as transactions
    # dkb should really fix their csv export, they should have the
    # money for that, right?
    csv_text = csv_text.splitlines()
    csv_text_filtered = []
    for line in csv_text:
        if "<br />" in line:
            continue
        else:
            csv_text_filtered.append(line)
    csv_text = "\n".join(csv_text_filtered)

    # deduplication
    if not args.input:
        if os.path.isfile(args.output + '.old'):
            logger.info("Checking for duplicates with %s" % args.output + '.old')
            with open(args.output + '.old', 'r') as fh:
                old_transactions = set(fh.read().decode(dummyqif.OUTPUT_CHARSET).splitlines()[start:])
                logger.info("Found %i old transactions (already stored)" % len(old_transactions))
                fh.close()
            csv_text = set(csv_text.splitlines()[start:])
            logger.info("Found %i transactions in the exported file" % len(csv_text))
            # have the new - the old transactions
            csv_text_diff = list(csv_text - old_transactions)
            logger.info("Found %i transactions in the exported file that are not old" % len(csv_text_diff))
            # naive sorting
            csv_text = '\n'.join(sorted(csv_text_diff, reverse=True))
            # append the additional transactions to the old transactions
            if (len(csv_text_diff) > 0):
                with open(args.output + '.old', 'a') as fh:
                    logger.info("Appending %i new transactions to %s" % (len(csv_text_diff), args.output + '.old'))
                    fh.write(csv_text.encode(dummyqif.OUTPUT_CHARSET))
                    fh.close()
        else:
            logger.info("Creating file of imported transactions %s" % args.output + ".old")
            transactions = csv_text.splitlines()[start:]
            logger.info("Found %i transactions and %i unique transactions" % (len(transactions), len(set(transactions))))
            with open(args.output + '.old', 'w') as fh:
                fh.write(csv_text.encode(dummyqif.OUTPUT_CHARSET))
                fh.close()

    if args.output == '-':
        f = sys.stdout
    else:
        if not re.match(r'^.*\.csv$', args.output):
            args.output += ".csv"
        f = open(args.output, 'w')

    if len(csv_text) > 0:
        logger.info("Writing new transactions to %s" % args.output)
        f.write(csv_text.encode(dummyqif.OUTPUT_CHARSET))

        # and now back again :(
        csv_text = csv_text.encode(dummyqif.INPUT_CHARSET)
        # always create the qiv file
        dkb2qif = dkb.DkbConverter(csv_text, cc_name=args.qif_account)
        if args.baid:
            # reconfigure the columns so they match the format for the banking-account
            '''
            banking account fields:
            0 "Buchungstag";
            1 "Wertstellung";
            2 "Buchungstext";
            3 "Auftraggeber / Begünstigter";
            4 "Verwendungszweck";
            5 "Kontonummer";
            6 "BLZ";
            7 "Betrag (EUR)";
            8 "Gläubiger-ID";
            9 "Mandatsreferenz";
            10 "Kundenreferenz";

            visa card fields:
            0 "Umsatz abgerechnet";
            1 "Wertstellung";
            2 "Belegdatum";
            3 "Beschreibung";
            4 "Betrag (EUR)";
            5 "Ursprünglicher Betrag";
            '''

            dkb2qif.COL_DATE = 1
            dkb2qif.COL_VALUTA_DATE = 1
            dkb2qif.COL_DESC = 4
            dkb2qif.COL_VALUE = 7
            dkb2qif.COL_INFO = 3
            dkb2qif.SKIP_LINES = 7

        if re.match(r'^.*\.csv$', args.output):
            args.output = re.sub(r'\.csv$', '', args.output) + ".qif"
        elif not re.match(r'^.*\.qif$', args.output):
            args.output = args.output + ".qif"

        #dkb2qif.export_to(args.output)

        # keep all the old .qif files, so the history of transactions is reproducible
        # and the files sort by date
        file_name = os.path.join(os.path.dirname(args.output),
                os.path.basename(args.output).split(".")[0] + "_" + \
                datetime.now().strftime("%Y-%m-%d_%H%M%S")) + ".qif"
        logger.info("Writing unique transactions to unique file: %s" % file_name)
        dkb2qif.export_to(file_name)
    else:
        logger.info("Doing nothing, no new transactions.")


"""
Testing:

1. Everything you could do with dkb.py, you still can do exactly the same way:

./dkbweb.py --userid USER --cardid 1234 --from-date 01.01.2015 --output cc.csv --raw

2. With dkbweb.py you can also query your bank account transactions:

./dkbweb.py --userid USER --baid 1234567890 --from-date 01.01.2015 --output ba.csv --raw

3. With dkbweb.py you can also directly submit your PIN to the command line:

./dkbweb.py --userid USER --pin 5x6y7z --cardid 1234 --output cc.qif

4. Also, dkbweb.py logs out the user before quitting the application.

Use with care!  This is very insecure because your PIN is submitted in plain text.
But this can be very handy for automation (batch scripting).
Use only if you know what you're doing!
"""
