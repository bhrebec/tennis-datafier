#!/usr/bin/env python
"""
tennis-datafier - collect and query tennis match data

Only supports the WTA at present, but could be extended to ATP with very
little trouble (5 set matches are the only issue).
"""

import sqlite3
import argparse
import codecs
import itertools 
import re
import math
import readline
import logging

import drawsheet;

def parse_score_components(score):
    score_re = re.compile(
            r"(?P<score>((?P<w1>[0-7])[/-]?(?P<l1>[0-7])(\((?P<tb1>\d+)\))?)"
                     r"( (?P<w2>[0-7])[/-]?(?P<l2>[0-7])(\((?P<tb2>\d+)\))?)?"
                     r"( (?P<w3>\d\d?)[/-]?(?P<l3>\d\d?)(\((?P<tb3>\d+)\))?)?"
            r"( ([Rr]et\.|[Rr]et'd|[Rr]etired|[Rr]et))?"
            r"|([Ww][Oo]\.?|[Ww]alkover))")
    
    m = score_re.match(score)
    if m == None:
        return [score] * 2 + [None] * 8
    else:
        d = m.groupdict()
        return [d['score'], 
                d['w1'], d['l1'], d['tb1'], 
                d['w2'], d['l2'], d['tb2'], 
                d['w3'], d['l3'], d['tb3'],
                ]

def get_date_clause(start, end):
    if not start and not end:
        return ''

    clause = ' AND ('
    if start:
         clause += "date >= '{}'".format(start)
    if start and end:
         clause += ' AND '
    if end:
         clause += "date <= '{}'".format(end)
    clause += ') '
    return clause

class db:
    def __init__(self, dbfile):
        self.DB_VERSION = 1
        self.conn = sqlite3.connect(dbfile);
        c = self.conn.cursor()
        try: 
            c.execute('SELECT value FROM info WHERE key="version"')
            version = c.fetchone()[0]

            c.close()
        except sqlite3.DatabaseError:
            print('Creating new database')
            version = 0

        self.update_db(version)

        self.conn.create_function('rivals_sort', 2, self.rivals_sort)

    def rivals_sort(self, wins, losses):
        diff = abs(wins - losses) * 2
        total = wins + losses

        return total - diff

    def update_db(self, version):
        c = self.conn.cursor()

        if (version < 1): # new db
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('CREATE TABLE info(key PRIMARY KEY, value)')
            c.execute('CREATE TABLE player(p_id INTEGER PRIMARY KEY, '
                    'firstname, lastname, country) ')
            c.execute('CREATE TABLE tournament(t_id INTEGER PRIMARY KEY, '
                    'city, name, country, date, '
                    'surface, class, '
                    'UNIQUE (city, country, name, date, class, surface))')
            c.execute('CREATE TABLE player_tournament('
                    't_id NOT NULL REFERENCES tournament(t_id), '
                    'p_id NOT NULL REFERENCES player(p_id), '
                    'status)')
            c.execute('CREATE TABLE match('
                    'round, '
                    't_id NOT NULL REFERENCES tournament(t_id), '
                    'winner NOT NULL REFERENCES player(p_id), '
                    'loser REFERENCES player(p_id), score, '
                    'score_w_1, score_l_1, score_w_2, score_l_2, '
                    'score_w_3, score_l_3, score_tb_1, score_tb_2, '
                    'score_tb_3, PRIMARY KEY(round, t_id, winner, loser))')

        c.execute('INSERT OR REPLACE INTO info(key, value) VALUES (?, ?)',
            ['version', self.DB_VERSION])
        self.conn.commit()
        c.close()


    def insert_tournament_manually(self):
        def enter_new_player(c):
            first = input('First name: ')
            last = input('Last name: ')
            country = input('Country Code: ')
            c.execute('INSERT INTO player '
                '(firstname, lastname, country) ' 
                'VALUES (?, ?, ?)', 
                [first, last, country])
            return c.lastrowid

        def get_player(prompt, t_id, c):
            pids = []

            player = input(prompt)
            if not player:
                return None

            pids = self.get_pids(player, c)
            if len(pids) == 0:
                confirm = input('Player not found - are they new? [y/N]')
                if confirm in ['Y', 'y']:
                    pid = [enter_new_player(c)]
                else:
                    return None
            elif len(pids) == 1:
                pid = pids[0]
            elif len(pids) > 1:
                for p in pids:
                    name = self.namefl(p, c)
                    print('{} - {}'.format(p, name))

                pid = int(input('{} players found, pick one:'.
                    format(len(pids))))

            name = self.namefl(pid, c)

            c.execute('SELECT * FROM player_tournament ' 
                'WHERE p_id=? AND t_id=?', [pid, t_id])

            r = c.fetchone()
            if r == None:
                seed = input('Enter seed for {}: '.format(name))
                # first entry in tournament
                c.execute('INSERT INTO player_tournament '
                    '(p_id, t_id, status) ' 
                    'VALUES (?, ?, ?)', 
                    [pid, t_id, seed])

            return pid

        c = self.conn.cursor()

        t_name = input('Enter tournament name: ')
        t_city = input('Enter tournament city: ')
        t_country = input('Enter tournament country: ')
        t_date = input('Enter tournament date (YYYY-MM-DD): ')
        t_surface = input('Enter tournament surface: ')
        t_class = input('Enter tournament class: ')

        t_info = (t_city, t_name, t_country, t_date, t_surface, t_class)
        t_id = self.tournament_id(c, t_info, insert=True)
        self.conn.commit()

        while True:
            round_ = input('Enter round designation (leave blank to finish): ')
            if not round_:
                break

            while True:
                winner = get_player( 'Enter winner (blank to finish): ', 
                        t_id, c)
                if not winner:
                    break

                loser = get_player('Enter loser (blank for bye): ',
                        t_id, c)

                score = input('Enter score in format: '
                        'wo|6-1 6-3 4-1 retd|6-1(1) 6-3(9) 20-18: ')
                matches = re.match(
                        r'(?:'
                        r'(\d+)-(\d+)(?:\((\d+)\))?'
                        r'(?: (\d+)-(\d+)(?:\((\d+)\))?)?'
                        r'(?: (\d+)-(\d+)(?:\((\d+)\))?)?'
                        r'(?: retd)?)|wo', 
                        score)
                scores = [score] + list(matches.groups())
                print('{}-{} ({}) {}-{} ({}) {}-{} ({})'.
                        format(*matches.groups()))

                c.execute('INSERT OR REPLACE INTO match'
                        '(round, t_id, winner, loser, score, '
                        ' score_w_1, score_l_1, score_tb_1,'
                        ' score_w_2, score_l_2, score_tb_2,'
                        ' score_w_3, score_l_3, score_tb_3)'
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        [round_, t_id, winner, loser] + scores)

                w_n = self.namefl(winner, c)
                l_n = self.namefl(loser, c)
                confirm = input('{}: {} v. {} - {} OK? [Y/n]: '.format(
                    round_, w_n, l_n, score))
                if confirm in ['n', 'N']:
                    self.conn.rollback()
                else:
                    self.conn.commit()

        c.close()


    def insert_file_drawsheet(self, filename, qualies):
        md, qd = drawsheet.process_pdf(filename, qualies)

        if md:
            draw, status, meta = md
            self.database_insert_drawsheet(draw, status, meta, False)

        if qd:
            draw, status, meta = qd
            self.database_insert_drawsheet(draw, status, meta, True)


    def database_insert_drawsheet(self, draw, status, meta, qualifying):
        """
        Enter the drawsheet into the database
        """
        c = self.conn.cursor()

        def check_player(name, info, t_id):
            stat, country = info
            last, sep, first = name.partition(', ')

            added = 0
            c.execute('SELECT p_id FROM player ' 
                'WHERE lower(firstname)=? AND lower(lastname)=?', 
                [first.lower(), last.lower()])

            r = c.fetchone()
            if r == None: # player is new, insert her
                # capitalize last name properly
                last = last.lower()
                last = ' '.join([(n[0].upper() + n[1:]) 
                    for n in last.split()])
                last = '-'.join([(n[0].upper() + n[1:]) 
                    for n in last.split('-')])

                added = 1
                c.execute('INSERT INTO player '
                    '(firstname, lastname, country) ' 
                    'VALUES (?, ?, ?)', 
                    [first, last, country])
                p_id = c.lastrowid
            else:
                p_id = r[0]

            c.execute('SELECT * FROM player_tournament ' 
                'WHERE p_id=? AND t_id=?', [p_id, t_id])

            r = c.fetchone()
            if r == None:
                # first entry in tournament
                c.execute('INSERT INTO player_tournament '
                    '(p_id, t_id, status) ' 
                    'VALUES (?, ?, ?)', 
                    [p_id, t_id, stat])

            return p_id, added

        print()
        if qualifying:
            print("Adding qualifying draw to database... ")
        else:
            print("Adding main draw to database... ")

        match_count = 0
        player_add_count = 0

        # insert the tournament as needed
        t_info = (meta['City'], meta['Name'], meta['Country'], 
            meta['Date'], meta['Surface'], meta['Class'])

        t_id = self.tournament_id(c, t_info, insert=True)

        # get player ids, insert missing players, enter player into tourney
        p_ids = {}
        for p, info in status.items():
            p_ids[p], added = check_player(p, info, t_id)
            player_add_count += added

        c.execute('SELECT count(*) FROM match')
        pre_count = c.fetchone()[0]

        for rnd in range(1, len(draw)):
            if qualifying:
                rnd_string = 'q{}'.format(rnd)
            else:
                rnd_string = 'R{}'.format(rnd)

            for result in draw[rnd]:
                winner = p_ids[result[0]]
                try:
                    loser = p_ids[result[3]]
                except KeyError:
                    loser = None

                scores = parse_score_components(result[2])
                logging.debug("ADD: {}: {} v. {} - {}".
                            format(rnd_string, winner, loser, scores))

                c.execute('INSERT OR REPLACE INTO match'
                        '(round, t_id, winner, loser, score, '
                        ' score_w_1, score_l_1, score_tb_1,'
                        ' score_w_2, score_l_2, score_tb_2,'
                        ' score_w_3, score_l_3, score_tb_3)'
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        [rnd_string, t_id, winner, loser] + scores)
                match_count += 1

        c.execute('SELECT count(*) FROM match')
        post_count = c.fetchone()[0]
        add_count = post_count - pre_count
        match_count -= add_count

        print('Done! {} matches updated, {} matches added, {} players added.'.
                format(match_count, add_count, player_add_count))

        all_correct = input('Save? [Y/n]: ')
        if all_correct in ('n', 'N'):
            self.conn.rollback()
        else:
            self.conn.commit()

        c.close()


    def insert_file_text_data(self, filename):
        self.insert_file_text_data_encoding(filename, 'latin1')

    def insert_match_text_data(self, c, line, t_id):
        def parse_insert_player(p, info):
            last, first = [s.strip() for s in p.split(',')]
            info = [s.strip().lstrip('[') for s in info.split(']')]
            if len(info) == 0:
                country = ''
                status = ''
            elif len(info) == 1:
                country = info[0]
                status = ''
            else:
                country, status = info[:2]

            if country.isdigit():
                status = country
                country = ''

            c.execute('SELECT p_id FROM player ' 
                'WHERE firstname=? AND lastname=?', [first, last])
            r = c.fetchone()
            if r == None:
                # player is new, insert her
                c.execute('INSERT INTO player '
                    '(firstname, lastname, country) ' 
                    'VALUES (?, ?, ?)', 
                    [first, last, country])
                p_id = c.lastrowid
            else:
                p_id = r[0]

            c.execute('SELECT * FROM player_tournament ' 
                'WHERE p_id=? AND t_id=?', [p_id, t_id])

            r = c.fetchone()
            if r == None:
                # first entry in tournament
                c.execute('INSERT INTO player_tournament '
                    '(p_id, t_id, status) ' 
                    'VALUES (?, ?, ?)', 
                    [p_id, t_id, status])
            return p_id

        def parse_score(score):
            score = score.strip()
            if score.replace(' ', '').replace('.', '').isalpha():
                return [score] + [None] * 8
            
            sets = (score.split(' ') + [None] * 3)[:3]
            results = []
            for s in sets:
                if s == None:
                    results += [None, None, None]
                else:
                    if '(' in s:
                        # tiebreak
                        games, tb = s.split('(')
                        tb = tb.rstrip(')')
                    else:
                        games = s
                        tb = None

                    if '-' in games:
                        w, l = games.split('-')
                        results += [w, l, tb]
                    else:
                        results += [None, None, None]

            return results

        rnd, sep, rest = line.partition('"')
        rnd = rnd.strip()
        p1, sep, rest = rest.partition('"')
        p1_info, sep, rest = rest.partition(' ')

        bye = False
        if rest.strip() == 'bye;':
            bye = True
            score = 'bye'
            p2 = None
        else:
            rest = rest.partition('"')[2]
            p2, sep, rest = rest.partition('"')
            p2_info, sep, rest = rest.partition(' ')
            score = rest.partition(';')[0]

        p1_id = parse_insert_player(p1, p1_info)

        if not bye:
            p2_id = parse_insert_player(p2, p2_info)
        else:
            p2_id = None

        score_list = parse_score(score)
        logging.debug(p1, 'vs', p2)
        c.execute('INSERT OR REPLACE INTO match'
                '(round, t_id, winner, loser, score, '
                ' score_w_1, score_l_1, score_tb_1,'
                ' score_w_2, score_l_2, score_tb_2,'
                ' score_w_3, score_l_3, score_tb_3)'
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                [rnd, t_id, p1_id, p2_id, score] + score_list)

    def insert_file_text_data_encoding(self, filename, encoding='utf8'):
        t_count = 0
        m_count = 0
        mu_count = 0
        c = self.conn.cursor()
        f = codecs.open(filename, 'r', encoding=encoding)
        t_id = -1
        inmatches = False
        intourney = False
        upd = False
        infoline = 0
        city, t_name, t_country, date, surface, t_class = [''] * 6
        for line in f:
            l = line.strip()
            if l == 'Start':
                intourney = True
                continue

            if not intourney:
                continue
            
            if l == ':':
                c.execute('SELECT t_id FROM tournament WHERE '
                        'city=? AND name=? AND country=? AND '
                        'date=? AND surface=? AND class=?',
                        [city, t_name, t_country, date, surface, t_class])
                r = c.fetchone()
                if r == None:
                    c.execute('INSERT INTO tournament'
                            '(city, name, country, date, surface, class)'
                            'VALUES (?,?,?,?,?,?)', 
                            [city, t_name, t_country, date, surface, t_class])
                    t_id = c.lastrowid
                else:
                    t_id = r[0]
                    upd = True
                    
                inmatches = True
                continue

            if l == 'Stop':
                inmatches = False
                intourney = False
                upd = False
                t_id = -1
                infoline = 0
                t_count += 1
                city, t_name, t_country, date, surface, t_class = [''] * 6
                continue

            if not inmatches:
                if infoline == 0:
                    city, t_name, t_country = [s.strip() for s in l.split(';')[:3]]
                    infoline = 1
                elif infoline == 1:
                    date, surface, t_class = [s.strip() for s in l.split(';')[:3]]
                    infoline = 2
            else:
                self.insert_match_text_data(c, l, t_id)

                if upd:
                    mu_count += 1
                else:
                    m_count += 1

        print('{}: Added {} matches and updated {} matches in {} tournaments'.
                format(filename, m_count, mu_count, t_count))
        f.close()
        self.conn.commit()
        c.close()

    def tournament_id(self, cursor, info, insert):
        city, t_name, t_country, date, surface, t_class = info
        cursor.execute('SELECT t_id FROM tournament WHERE '
                'city=? AND name=? AND country=? AND '
                'date=? AND surface=? AND class=?',
                [city, t_name, t_country, date, surface, t_class])
        r = cursor.fetchone()
        if r == None:
            if insert:
                cursor.execute('INSERT INTO tournament'
                        '(city, name, country, date, surface, class)'
                        'VALUES (?,?,?,?,?,?)', 
                        [city, t_name, t_country, date, surface, t_class])
                return cursor.lastrowid
            else:
                return None
        else:
            return r[0]

    def namefil(self, pid, c = None):
        if c == None:
            c = self.conn.cursor()

        c.execute('SELECT firstname, lastname FROM player WHERE p_id=?',
                (pid,))
        n = c.fetchone()
        if n == None:
            return ''

        return n[0][0] + '. ' + n[1]

    def namefl(self, pid, c = None):
        if c == None:
            c = self.conn.cursor()

        c.execute('SELECT firstname, lastname FROM player WHERE p_id=?', (pid,))
        n = c.fetchone()
        if n == None:
            return ''

        return n[0] + ' ' + n[1]

    def namelf(self, pid, c = None):
        if c == None:
            c = self.conn.cursor()

        c.execute('SELECT firstname, lastname FROM player WHERE p_id=?',
                (pid,))
        n = c.fetchone()
        if n == None:
            return ''

        return n[1] + ', ' + n[0]


    def get_pids(self, name, c = None):
        if c == None:
            c = self.conn.cursor()

        if ',' in name:
            l, f = [s.strip() for s in name.split(',', 1)]
        else:
            if ' ' in name:
                f, l = [s.strip() for s in name.split(' ', 1)]
            else:
                l = name.strip()
                f = None

        if f == None:
            c.execute('SELECT p_id FROM player WHERE lastname GLOB ?', 
                    [l + '*'])

            a = c.fetchall()
            if a == []:
                c.execute('SELECT p_id FROM player WHERE firstname GLOB ?', 
                        [l + '*'])
                a = c.fetchall()
        else:
            c.execute('SELECT p_id FROM player '
                    'WHERE firstname GLOB ? AND lastname GLOB ?', 
                    [f, l])

            a = c.fetchall()
            if a == []:
                c.execute('SELECT p_id FROM player '
                        'WHERE firstname GLOB ? AND lastname GLOB ?', 
                        [f + '*', l + '*'])
                a = c.fetchall()

        return [i[0] for i in a]

    def print_matches(self, pid, n=None, start=None, end=None):
        c = self.conn.cursor()
        if n:
            limit = 'LIMIT {}'.format(n)
        else:
            limit = ''

        c.execute('SELECT date, city, class, round, '
                ' winner, p1.status AS p1s, '
                'loser, p2.status AS p2s, score, surface ' 
                'FROM match '
                    'NATURAL INNER JOIN tournament '
                    'INNER JOIN player_tournament AS p1 ON '
                        'p1.p_id=match.winner AND '
                        'p1.t_id=match.t_id '
                    'INNER JOIN player_tournament AS p2 ON '
                        'p2.p_id=match.loser AND '
                        'p2.t_id=match.t_id '
                'WHERE (winner==? OR loser==?) '
                + get_date_clause(start, end) +
                'ORDER BY date DESC ' + limit, 
                [pid, pid])
        matches = c.fetchall()

        for m in matches:
            print('{} - {} {}: {} {}({}) d. {}({}) {} {}'.format(
                m[0], m[1], m[2], m[3], self.namefil(m[4]),
                m[5], self.namefil(m[6]), m[7], m[8], m[9]))

    def action_matches(self, players, start, end):
        c = self.conn.cursor()

        pids = []
        for p in players:
            pids += self.get_pids(p, c)

        for p in pids:
            print()
            print("Record for {}:".format(self.namefl(p)))
            self.print_matches(p, start=start, end=end)

    def action_tournament(self, t_fuzzy, start, end):
        c = self.conn.cursor()

        c.execute('SELECT t_id, city, country, name, class FROM tournament WHERE '
                '(city=? OR name=? OR country=? OR '
                'surface=? OR class=?) ' + get_date_clause(start, end)
                + ' ORDER BY date ASC'
                , [t_fuzzy, t_fuzzy, t_fuzzy, t_fuzzy, t_fuzzy])
        tournaments = c.fetchall()

        for t, city, country, name, class_ in tournaments:
            print('{}: {}, {} - {}'.format(name, city, country, class_))
            c.execute('SELECT date, city, class, round, '
                    ' winner, p1.status AS p1s, '
                    'loser, p2.status AS p2s, score, surface ' 
                    'FROM match '
                        'NATURAL INNER JOIN tournament '
                        'INNER JOIN player_tournament AS p1 ON '
                            'p1.p_id=match.winner AND '
                            'p1.t_id=match.t_id '
                        'INNER JOIN player_tournament AS p2 ON '
                            'p2.p_id=match.loser AND '
                            'p2.t_id=match.t_id '
                    'WHERE tournament.t_id=?'
                    'ORDER BY round ASC ', 
                    [t])
            matches = c.fetchall()

            for m in matches:
                print('{} - {} {}: {} {}({}) d. {}({}) {} {}'.format(
                    m[0], m[1], m[2], m[3], self.namefil(m[4]),
                    m[5], self.namefil(m[6]), m[7], m[8], m[9]))
            print()


    def print_record(self, pid, start, end):
        def make_percent(wins, losses):
            if wins + losses == 0:
                return 'Inf'
            else:
                return float(wins) / (wins + losses)

        c = self.conn.cursor()
        c.execute('SELECT count(*) ' 
                'FROM match NATURAL INNER JOIN tournament '
                'WHERE winner=? AND loser IS NOT NULl'
                + get_date_clause(start, end)
                , [pid])
        wins = c.fetchone()[0]

        c.execute('SELECT count(*) ' 
                'FROM match NATURAL INNER JOIN tournament WHERE loser=?'
                + get_date_clause(start, end)
                , [pid])
        losses = c.fetchone()[0]


        c.execute('SELECT surface, count(*) ' 
                'FROM match NATURAL INNER JOIN tournament WHERE winner=? '
                + get_date_clause(start, end) +
                'AND loser IS NOT NULl GROUP BY surface', [pid])
        surface_wins = dict(c.fetchall())

        c.execute('SELECT surface, count(*) ' 
                'FROM match NATURAL INNER JOIN tournament '
                'WHERE loser=? '
                + get_date_clause(start, end) +
                'GROUP BY surface', [pid])
        surface_losses = dict(c.fetchall())

        surface_record = {}
        for s, w in surface_wins.items():
            if s in surface_losses:
                surface_record[s] = (w, surface_losses[s])
                del surface_losses[s]
            else:
                surface_record[s] = (w, 0)

        for s, w in surface_losses.items():
            surface_record[s] = (0, w)

        print("Overall Record: {} matches played, {}-{} ({:.3})".
                format(wins + losses, wins, losses, 
                    make_percent(wins, losses)))

        indoor_record = (0,0)
        summary_record = {
                'Clay' : (0,0),
                'Hard' : (0,0),
                'Grass' : (0,0),
                'Carpet' : (0,0),
                }
        for s, (w, l) in sorted(surface_record.items(), key=lambda a: a[0]):
            if s.startswith('Indoor'):
                c_w, c_l = indoor_record
                indoor_record = (c_w + w, c_l + l)

            for sr, (c_w, c_l) in summary_record.items():
                if s.endswith(sr):
                    summary_record[sr] = (c_w + w, c_l + l)

            print("\t... on {}: {} matches played, {}-{} ({:.3})".
                    format(s, w+l, w, l, make_percent(w, l)))

        print("\tin Summary:")

        for s, (w, l) in summary_record.items():
            print("\tAll {}: {} matches played, {}-{} ({:.3})".
                    format(s, w+l, w, l, make_percent(w, l)))
        w, l = indoor_record
        print("\tRecord Indoors: {} matches played, {}-{} ({:.3})".
                format(w+l, w, l, make_percent(w, l)))


    def action_record(self, players, start, end):
        c = self.conn.cursor()

        pids = []
        for p in players:
            pids += self.get_pids(p, c)

        for p in pids:
            self.print_record(p, start, end)


    def action_profile(self, players, start, end):
        c = self.conn.cursor()

        pids = []
        for p in players:
            pids += self.get_pids(p, c)

        for p in pids:
            print()
            print("Profile for {}:".format(self.namefl(p)))

            c.execute('SELECT country ' 
                    'FROM player WHERE p_id=?', [p])
            country = c.fetchone()[0]

            print("Country: {}".format(country))
            self.print_record(p, start, end)
            print()
            print("Last 10 matches:")
            self.print_matches(p, 10, start=start, end=end)

        c.close()

    def action_undefeated(self, players, start, end):
        c = self.conn.cursor()

        pids = []
        for p in players:
            pids += self.get_pids(p, c)

        for p in pids:
            print()
            print("Players {} is undefeaded vs.:".format(self.namefl(p)))
            c.execute("""
                SELECT loser, count(winner)
                FROM match as w
                WHERE winner=? AND loser IS NOT NULL AND NOT EXISTS (
                    SELECT * FROM match NATURAL INNER JOIN tournament as l 
                        WHERE loser=? AND l.winner=w.loser """
                        + get_date_clause(start, end) + """)
                GROUP BY loser
                ORDER BY count(winner) DESC""", [p] * 2)

            players = c.fetchall()
            for pl in players:
                print("{}-0 vs. {}".format(pl[1], self.namefl(pl[0])))

            print()
            print("Players undefeaded vs. {}:".format(self.namefl(p)))
            c.execute("""
                SELECT winner, count(loser)
                FROM match as l
                WHERE loser=? AND NOT EXISTS (
                    SELECT * FROM match NATURAL INNER JOIN tournament as w 
                        WHERE winner=? AND w.loser=l.winner """
                        + get_date_clause(start, end) + """)
                GROUP BY winner
                ORDER BY count(winner) DESC""", [p] * 2)

            players = c.fetchall()
            for p in players:
                print("0-{} vs. {}".format(p[1], self.namefl(p[0])))

        c.close()

    def action_best_worst(self, players, n, operation='best', start=None, end=None):
        c = self.conn.cursor()

        pids = []
        for p in players:
            pids += self.get_pids(p, c)

        if operation == 'best':
            order = ('ORDER BY (wins.win_count - losses.loss_count) DESC, '
                    '(wins.win_count + losses.loss_count) DESC')
        elif operation == 'worst':
            order = ('ORDER BY (wins.win_count - losses.loss_count) ASC, '
                    '(wins.win_count + losses.loss_count) DESC')
        elif operation == 'rivals':
            order = ('ORDER BY '
                'rivals_sort(wins.win_count, losses.loss_count) DESC')
        else:
            print("invalid op in best_worst()")
            return

        d_c = get_date_clause(start, end)

        for p in pids:
            # sqlite doesn't support FULL OUTER JOIN, this is the workaround
            c.execute("""
         SELECT wins.opponent, wins.win_count, losses.loss_count
            FROM (SELECT winner as player, 
                    loser as opponent, count(*) as win_count
                    FROM match NATURAL INNER JOIN tournament
                    WHERE winner=? AND loser IS NOT NULL """ + d_c + """
                    GROUP BY loser
                UNION ALL 
                SELECT DISTINCT loser as player, 
                        winner as opponent, 0 as win_count
                    FROM match as l NATURAL INNER JOIN tournament
                    WHERE loser=? AND NOT EXISTS (
                        SELECT * FROM match as w NATURAL INNER JOIN tournament
                            WHERE winner=? AND w.loser=l.winner """ + d_c + """)
                        """ + d_c + """
                ) AS wins
                INNER JOIN
                (SELECT loser as player, winner as opponent, 
                        count(*) as loss_count
                    FROM match NATURAL INNER JOIN tournament
                    WHERE loser=? """ + d_c + """
                    GROUP BY winner
                UNION ALL 
                SELECT DISTINCT winner as player, loser as opponent, 
                        0 as loss_count
                    FROM match as w NATURAL INNER JOIN tournament
                    WHERE winner=? AND loser IS NOT NULL AND NOT EXISTS (
                        SELECT * FROM match as l NATURAL INNER JOIN tournament
                            WHERE loser=? AND l.winner=w.loser """ + d_c + """)
                        """ + d_c + """
                ) AS losses
                ON wins.player==losses.player 
                    AND wins.opponent==losses.opponent """
            + order + " LIMIT " + n, [p] * 6)

            recordvs = c.fetchall()

            if operation == 'best':
                print("{} - {} opponents defeated most:".format(self.namefl(p), n))
            elif operation == 'worst':
                print("{} - {} opponents defeated least:".format(self.namefl(p), n))
            elif operation == 'rivals':
                print("{} - {} biggest rivals:".format(self.namefl(p), n))

            for e in recordvs:
                print("{}-{} vs. {}".format(e[1], e[2],
                    self.namefl(e[0])))

        c.close()

    def action_h2h(self, players, start, end):
        c = self.conn.cursor()

        pids = []
        for p in players:
            pids += self.get_pids(p, c)


        if len(pids) > 10:
            print("{} players found: only doing h2h for first 10".format(len(pids)))
            pids = pids[:10]

        for p1, p2 in itertools.combinations(pids, 2):
            c.execute('SELECT count(winner) ' 
                    'FROM match NATURAL INNER JOIN tournament '
                    'WHERE winner=? AND loser=?'
                        + get_date_clause(start, end)
                    , [p1, p2])
            p1wins = c.fetchone()[0]

            c.execute('SELECT count(winner) ' 
                    'FROM match NATURAL INNER JOIN tournament '
                    'WHERE winner=? AND loser=?'
                        + get_date_clause(start, end)
                    , [p2, p1])
            p2wins = c.fetchone()[0]

            c.execute('SELECT date, city, class, round, '
                    ' winner, p1.status AS p1s, '
                    'loser, p2.status AS p2s, score, surface ' 
                    'FROM match '
                        'NATURAL INNER JOIN tournament '
                        'INNER JOIN player_tournament AS p1 ON '
                            'p1.p_id=match.winner AND '
                            'p1.t_id=match.t_id '
                        'INNER JOIN player_tournament AS p2 ON '
                            'p2.p_id=match.loser AND '
                            'p2.t_id=match.t_id '
                    'WHERE winner IN (?,?) AND loser IN (?,?)' 
                        + get_date_clause(start, end) + 
                    'ORDER BY date DESC', 
                    [p1, p2] * 2)
            matches = c.fetchall()

            print(self.namefl(p1) + ' vs. ' + self.namefl(p2))
            print(str(p1wins) + '-' + str(p2wins))
            
            names = {}
            names[p1] = self.namefil(p1)
            names[p2] = self.namefil(p2)
            for m in matches:
                print('{} - {} {}: {} {}({}) d. {}({}) {} {}'.format(
                    m[0], m[1], m[2], m[3], names[m[4]], 
                    m[5], names[m[6]], m[7], m[8], m[9]))

            print()
        c.close()
            


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Query a tennis-datafier database')

    parser.add_argument('--debug', action='store_true', 
            help='Debug output')
    parser.add_argument('-d', '--database', default='tennis.db',
            metavar='FILE',
            help='Database to operate on (default is tennis.db)')
    parser.add_argument('players', metavar="PLAYER", nargs='*', 
            help='players to operate on')

    # actions
    parser.add_argument('-p', '--profile', action='store_true',
            help='Look up profiles for players')
    parser.add_argument('-2', '--h2h', action='store_true',
            help='Look up h2h for given players')
    parser.add_argument('-c', '--matches', action='store_true', 
            help='Get complete match record for this player')
    parser.add_argument('-o', '--tournament', metavar='TOURNY', 
            help='Get complete tournament record')
    parser.add_argument('-r', '--rivals', metavar='N', 
            help='Look up the N biggest rivals for given players')
    parser.add_argument('-b', '--best', metavar='N', 
            help='Look up the best N opponents for given players')
    parser.add_argument('-w', '--worst', metavar='N', 
            help='Look up the best N opponents for given players')
    parser.add_argument('-u', '--undefeated', action='store_true',
            help='Look up the undefeated records for given players')
    parser.add_argument('-t', '--text-data', metavar='FILE', action='append',
            help='add a file in the old text-data input format to the db')
    parser.add_argument('-9', '--wtadraw', metavar='FILE', action='append',
            help='add a file in wta drawsheet format (requires pdftotext)')
    parser.add_argument('-a', '--add', action='store_true',
            help='add a tournament by hand')
    parser.add_argument('-q', '--qualifying', action='store_true',
            help='Only import qualifying draw')
    parser.add_argument('-s', '--start', metavar="DATE",
            default=None,
            help='Restrict results to after this date')
    parser.add_argument('-e', '--end', metavar="DATE",
            default=None,
            help='Restrict results to after this date')

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    d = db(args.database)

    if args.text_data:
        for i in args.text_data:
            d.insert_file_text_data(i)
    elif args.wtadraw:
        for i in args.wtadraw:
            d.insert_file_drawsheet(i, args.qualifying)
    elif args.h2h:
        d.action_h2h(args.players,
                args.start, args.end)
    elif args.tournament:
        d.action_tournament(args.tournament, args.start, args.end)
    elif args.profile:
        d.action_profile(args.players,
                args.start, args.end)
    elif args.matches:
        d.action_matches(args.players,
                args.start, args.end)
    elif args.best:
        d.action_best_worst(args.players, args.best, 'best', 
                args.start, args.end)
    elif args.worst:
        d.action_best_worst(args.players, args.worst, 'worst',
                args.start, args.end)
    elif args.rivals:
        d.action_best_worst(args.players, args.rivals, 'rivals',
                args.start, args.end)
    elif args.undefeated:
        d.action_undefeated(args.players,
                args.start, args.end)
    elif args.add:
        d.insert_tournament_manually()
    else:
        parser.print_help()


