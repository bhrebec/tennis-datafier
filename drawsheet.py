#!/usr/bin/env python
"""
Parses pdf tennis drawsheets. 

Relies on poppler's (http://poppler.freedesktop.org/) pdftotext utility; it must
be on path for the drawsheet importer to function.
"""

import re
import subprocess
import readline
import math
import pprint
import logging

################################
# Utility Functions            #
################################

RE_MONTHS = [r'Jan(\.|uary)?', 
          r'Feb(\.|ruary)?', 
          r'Mar(\.|ch)?',
          r'Apr(\.|il)?',
          r'May',
          r'Jun(\.|e)?',
          r'Jul(\.|y)?',
          r'Aug(\.|ust)?',
          r'Sep(\.|tember)?',
          r'Sept(\.|ember)?',
          r'Oct(\.|ober)?',
          r'Nov(\.|ember)?',
          r'Dec(\.|ember)?',
      ]
"""regexs for matching month names"""


def month_to_int(month):
    """convert month to int"""
    # TODO: combine with above
    MONTH_TABLE = ((r'Jan(\.|uary)?', 1),
              (r'Feb(\.|ruary)?', 2),
              (r'Mar(\.|ch)?', 3),
              (r'Apr(\.|il)?', 4),
              (r'May', 5),
              (r'Jun(\.|e)?', 6),
              (r'Jul(\.|y)?', 7),
              (r'Aug(\.|ust)?', 8),
              (r'Sep(\.|tember)?', 9),
              (r'Sept(\.|ember)?', 9),
              (r'Oct(\.|ober)?', 10),
              (r'Nov(\.|ember)?', 11),
              (r'Dec(\.|ember)?', 12),
          )
    for m in MONTH_TABLE:
        if re.match(m[0], month):
            return m[1]

    return None

n_month = r"(?P<month>{})".format('|'.join(RE_MONTHS))
date_re = (
        re.compile(r"(?P<day>\d{1,2})(th)? ?- ?\d{1,2}(th)? " + 
            n_month + r",? (?P<year>\d{4})"), 
        re.compile(n_month + 
            r" (?P<day>\d{1,2})(th)? ?- ?\d{1,2}(th)?,? (?P<year>\d{4})"), 
        re.compile(r"(?P<year>\d{4})(?P<month>)(?P<day>)"),
            )
"""3 regexs for matching dates"""

def normalize_dates(dates):
    """Takes a date string and output it as YYYY-MM-DD"""
    n_dates = []
    for date, pos in dates:
        for r in date_re:
            m = r.match(date)
            if m:
                d = m.groupdict()
                month = month_to_int(d['month'])
                day = d['day']
                year = d['year']
                if month and day:
                    n_dates += [('{}-{:02}-{:02}'.
                        format(year, int(month), int(day)),)]
                else:
                    n_dates += [('{}'.format(year),)]

                break

    n_dates.sort(key=lambda d: len(d), reverse=True)
    return n_dates

def process_pdf(filename, qualies_only=False):
    """
    Parse the pdf file in filename.

    Retuns a tuple (main_draw, qualifying_draw) where each component is:
        (draw, status, meta).
    """
    if filename.endswith('.txt'):
        f = open(filename)
        text = f.read()
        f.close()
    else:
        text = subprocess.check_output(["pdftotext", "-layout",
            filename, "-"]).decode('utf-8')

    print("Processing {}...".format(filename))

    pages = text.split(chr(12))
    print ("{} Pages".format(len(pages)))
    md = []
    qd = []
    for p in pages:
        if ('MAIN DRAW SINGLES' in p or 'Singles Championship' in p
                or 'Ladies\' Singles' in p):
            md += [p]
        elif ('QUALIFYING SINGLES' in p or 'Qualifying Singles' in p
                or 'Qualifying Ladies\' Singles' in p):
            qd += [p]
        elif ('Qualifiers' in p and not 'Doubles' in p):
            qd += [p]

    md_result = None
    qd_result = None

    meta = None
    if md and not qualies_only:
        md_result = drawsheet_process(chr(12).join(md))
        meta = md_result[2]

    # copy the metadata to the quaily draw if possible
    if qd:
        qd_result = drawsheet_process(chr(12).join(qd), meta, True)

    return (md_result, qd_result)


def drawsheet_parse(text):
    """
    Parse the drawsheet into useful atoms
    """
    logging.debug("################ PARSING DRAW ##################")

    month = "({})".format('|'.join(RE_MONTHS))

    patterns = (
            ('surface', r"Hard|Outdoor Hard|Red Clay|Green Clay|Clay|"
                      r"Grass|Indoor Hard|Carpet|Indoor Carpet"),
            ('date', r"\d{1,2}(th)? ?- ?\d{1,2}(th)? " + month + r",? \d{4}|" +
                     month + r" \d{1,2}(th)? ?- ?\d{1,2}(th)?,? \d{4}"),
            ('year', r"\d{4}"),
            ('seed', r"(?<=\[)\d+(?=\])|(?<=\[ )\d+(?=\ ])"),
            ('round', r"(1st|2nd|3rd) Round|1/8|1/4|1/2"),
            ('class', r"WTA( [A-Za-z0-9]+)*|US Open|"
                      r"French Open|Australian Open|Wimbledon"),
            ('orderedname', r"[A-Z][a-z]+(( |-)[A-Z][a-z]+)*"
                            r" ([A-Z]+(( |-)[A-Z]+)*)(?= |$)"),
            ('fullname', r"(?:^| )[Bb][Yy][Ee](?:$| )|([A-Z]+(( |-)[A-Z]+)*,\s"
                              r"[A-Z][a-zA-Z]*(( |-)([A-Z][a-zA-Z]*[a-z]))*)"),
            #('shortname', r"[A-Z]\. ?[A-Z]+(( |-)[A-Z]+)*"),
            ('shortname', r"[A-Z]\. ?[A-Za-z]+(( |-)[A-Za-z]+)*"),
            ('country', r"(?:(?!RET)[A-Z]{3}|\([A-Z]{3}\))(?= |$)"),
            ('score',
                 r"([0-7][/-]?[0-7](\(\d+\))?)( [0-7][/-]?[0-7](\(\d+\))?){0,2}"
                 r" ([Rr]et\.|[Rr]et'd|[Rr]etired|[Rr]et)"
                 r"|([0-7][/-]?[0-7](\(\d+\))?)( [0-7][/-]?[0-7](\(\d+\))?){1,2}"
                 r"|([0-7]/?[0-7](\(\d+\))? ){2}[\d+]/[\d+]"
                 r"|(wo.|[Ww]alkover)"),
            ('prize', r"\$[0-9,]+(?= |$)"),
            ('number', r"\d{1,3}\.?(?= |$)"),
            ('city', r"[A-Z][A-Za-z]*( [A-Z][A-Za-z]+)*,"
                        r"( [A-Z][A-Z],)? (USA|[A-Z][a-z]*)"),
            ('status', r"(^|(?<=\[|\(| ))(Q|LL|W|WC)((?=\]|\)| )|$)"),
            ('string', r"([A-Za-z&,\']+)( [A-Z&a-z$,]+)*"),
            )
    
    pattern = re.compile('|'.join(["(?P<{}>{})".format(k, v) 
        for k, v in patterns]))
    data = { k: [] for k, v in patterns}

    short_to_fullnames = {}
    ordered_to_fullnames = {}
    def add_to_fullname_conversion_table(fullname, x, y):
        nm = re.match('(.*), (.)', fullname)
        name = nm.group(2) + ". " + nm.group(1)
        if name not in short_to_fullnames:
            short_to_fullnames[name] = []

        short_to_fullnames[name] += [(fullname, (x,y))]

        nm = re.match('(.*), (.*)', fullname)
        name = nm.group(2) + " " + nm.group(1)
        ordered_to_fullnames[name] = fullname


    re_skip = re.compile(r'Seeded +Players')
    # Find scores, names, etc
    y = 0
    skipping_page = False

    # collect the data
    width = 0
    lines = text.split('\n');
    for line in lines:
        if skipping_page:
            if chr(12) in line:
                skipping_page = False
            else:
                continue

        if (re_skip.search(line)):
            # skip the seeding/info section, it's useless
            skipping_page = True
            continue;

        for m in pattern.finditer(line):
            for group, match in m.groupdict().items():
                if match is not None:
                    match = match.strip()
                    x1 = m.start(group)
                    x2 = m.end(group)

                    if x2 > width:
                        width = x2

                    data[group] += [(match, ((x1, x2), y))]

                    if group == 'fullname' and match.upper() != "BYE":
                        add_to_fullname_conversion_table(match, (x1, x2), y)

        y += 1

    # hack to catch country codes that got attached to fullnames
    if len(data['country']) > 0:
        cc_re = re.compile(r'^([A-Z]{3}) (.*)')
        # find known country codes
        countries = set(list(zip(*data['country']))[0])
        if len(data['fullname']) > len(data['country']):
            for n, point in data['fullname']:
                m = cc_re.match(n)
                if m and m.group(1) in countries:
                    country = m.group(1)
                    name = m.group(2)
                    idx = data['fullname'].index((n, point))
                    del data['fullname'][idx]
                    (x1, x2), y = point
                    data['fullname'].insert(idx, (name, ((x1 + 4), x2, y)))
                    data['country'].append((country, ((x1, x1 + 3), y)))
                    add_to_fullname_conversion_table(name)
                    if len(data['fullname']) == len(data['country']):
                        # we're done
                        break

        # find any possible country codes
        if len(data['fullname']) > len(data['country']):
            for n, point in data['fullname']:
                m = cc_re.match(n)
                if m:
                    country = m.group(1)
                    name = m.group(2)
                    idx = data['fullname'].index((n, point))
                    del data['fullname'][idx]
                    (x1, x2), y = point
                    data['fullname'].insert(idx, (name, ((x1 + 4, x2), y)))
                    data['country'].append((country, ((x1, x1 + 3), y)))
                    add_to_fullname_conversion_table(name)
                    if len(data['fullname']) == len(data['country']):
                        # we're done
                        break

    orderednames = []
    for n, point in data['orderedname']:
        try:
            n = ordered_to_fullnames[n]
            orderednames += [(n, point)]
        except KeyError:
            data['string'] += [(n, point)]

    data['orderedname'] = orderednames

    def distance(a, b):
        ax1, ax2 = a[0]
        bx1, bx2 = b[0]
        ax = (ax1 + ax2) / 2
        bx = (bx1 + bx2) / 2
        dx = float(ax - bx) / 10
        dy = float(a[1] - b[1])

        return math.sqrt(dx * dx + dy * dy)

    # assign shortnames to longnames
    # some people share a shortname, so assign to 
    # the longname that is closest
    shortnames = []
    for n, point in data['shortname']:
        n = n.upper()
        if n[2] != ' ':
            short = n[0:2] + ' ' + n[2:]
        else:
            short = n

        try:
            shorts = short_to_fullnames[short]

            short = min(shorts, key=lambda s: distance(s[1], point))
            shortnames += [(short[0], point)]
        except KeyError:
            data['string'] += [(n, point)]

    data['shortname'] = shortnames

    logging.debug(pprint.pformat(data))

    return data, width;

def drawsheet_complete_draw(draw, wins, scores):
    """
    Given 'draw' with round 1 filled in, complete the draw
    """
    current_results = []
    next_results = []

    logging.debug("################ PROCESSING DRAW ###############")

    while len(wins) > 0 and len(draw[-1]) != 1:
        
        if len(draw[-1]) < 2:
            break

        logging.debug("ROUND OF {}".format(len(draw[-1])))
        rnd = []
        match = 0
        while len(rnd) < (len(draw[-1]) / 2) and len(wins) > 0:
            prev_a = draw[-1][match * 2]
            prev_b = draw[-1][match * 2 + 1]

            logging.debug("\tMatchup: {} v. {}".format(prev_a[0], prev_b[0]))

            candidates = []
            for p in (prev_a[0], prev_b[0]):
                if p in wins:
                    candidates = wins[p]

            if len(candidates) == 0:
                # There's something wrong, discard somebody and try again
                del draw[-1][match * 2]
                print("ERROR: Can't find winner for {} "
                        "v. {} in round of {}".
                        format(prev_a[0], prev_b[0], len(draw[-1])))
                continue

            ax, ay = prev_a[1]
            bx, by = prev_b[1]
            avg_x = (ax + bx) / 2

            candidates.sort(key=lambda e: abs(avg_x - e[1][0]))
            candidates.sort(key=lambda e: e[1][1] >= ay and e[1][1] <= by,
                    reverse=True)

            winner = candidates[0]
            del candidates[0]
            for p in (prev_a[0], prev_b[0]):
                if p in wins:
                    c = wins[p]
                    if len(c) == 0:
                        del wins[p]


            if prev_a[0].upper() == "BYE" or prev_b[0].upper() == "BYE":
                score = 'bye'
            else:
                score = drawsheet_get_score(winner, scores)

            logging.debug("\t\tWINNER {} ({})".format(winner[0], score))

            if winner[0] == prev_a[0]:
                loser = prev_b[0]
            else:
                loser = prev_a[0]

            rnd += [(winner[0], winner[1], score, loser)]
            match += 1

        draw += [rnd]

def drawsheet_get_score(player, scores):
    """
    Find the score closest to a given player
    """
    def distance(score, player):
        dx = float(score[0] - player[0]) / 5
        dy = float(score[1] - player[1])
        if dy < 0:
            dy *= 3

        return math.sqrt(dx * dx + dy * dy)

    if len(scores) == 0:
        return None

    scores.sort(key=lambda s: distance(s[1], player[1]))
    #print([(k, distance(k[1], player[1])) for k in scores[:3]])
    score = scores[0]
    del scores[0]

    return score[0]

def drawsheet_get_all_meta(data):
    """
    Try to parse the tourney metadata and prompt the user for 
    correctness.
    """
    def get_meta(prompt, default, default_list):
        default_count = 0
        if default_list:
            if not default:
                count = len(default_list)
                if count == 0:
                    default = ''
                else:
                    if type(default_list[0]) is str:
                        default = default_list[0]
                    else:
                        default = default_list[0][0]
                    default_count = count - 1

            readline.clear_history()
            default_list.reverse()
            for d in default_list:
                if type(d) is str:
                    readline.add_history(d)
                else:
                    readline.add_history(d[0])

        if default_count > 0:
            full_prompt = ('{} [{}](+ {} more): '.
                    format(prompt, default, default_count))
        else:
            full_prompt = ('{} [{}]: '.
                    format(prompt, default))

        result = input(full_prompt)
        if result == '':
            return default
        else:
            return result

    meta = dict.fromkeys((
        'Name', 'Class', 'City', 'Country', 'Surface', 'Date'))
    dates = normalize_dates(data['date'] + data['year'])

    names = data['string']
    surface = data['surface']
    cities = []
    countries = []
    for c, pos in data['city']:
        if ',' in c:
            city, part, country = c.partition(', ')
            cities += [city]
            countries += [country]
        else:
            countries += [country]

    classes = []
    for c, pos in data['class']:
        if c == "Wimbledon":
            names = ['The Championships'] + names
            cities = ['Wimbledon'] + cities
            classes = ['Grand Slam']
            countries = ['Great Britain'] + countries
            surface = ['Grass'] + surface
        elif c == "US Open":
            names = ['US Open'] + names
            cities = ['Flushing Meadows'] + cities
            classes = ['Grand Slam']
            countries = ['United States'] + countries
            surface = ['Hard'] + surface
        elif c == "French Open":
            names = ['French Open'] + names
            cities = ['Roland Garros'] + cities
            classes = ['Grand Slam']
            countries = ['France'] + countries
            surface = ['Red Clay'] + surface
        elif c == "Australian Open":
            names = ['Australian Open'] + names
            cities = ['Melbourne'] + cities
            classes = ['Grand Slam']
            countries = ['Australia'] + countries
            surface = ['Hard'] + surface
        else:
            if c[:3] == "WTA":
                classes += [c[4:]]
            else:
                classes += [c]

    all_correct = 'n'
    while all_correct in ('N', 'n'):
        print()
        meta['Name'] = get_meta("Name", meta['Name'], names)
        meta['Class'] = get_meta("Class", meta['Class'], classes)
        meta['Date'] = get_meta("Date", meta['Date'], dates)
        meta['City'] = get_meta("City", meta['City'], cities)
        meta['Country'] = get_meta("Country", meta['Country'], countries)
        meta['Surface'] = get_meta("Surface", meta['Surface'], surface)

        print()
        for k, v in sorted(meta.items()):
            print("{}: {}". format(k, v))

        all_correct = input('OK? [Y/n]: ')

    return meta

def drawsheet_players_status(draw, data):
    """
    Return dict of each player's status
    """

    logging.debug("######## CALCULATING STATUS ########")

    # 1. Discard draw position for each player
    # 2. Find players for seeding or Q or WC or LL status
    # 3. Find country for each player

    def distance2(number, player):
        dx = float(number[0] - player[0]) / 20
        dy = float(number[1] - player[1])

        return math.sqrt(dx * dx + dy * dy)

    def distance(number, player):
        dx = float(number[0] - player[0]) / 10
        dy = float(number[1] - player[1])

        return math.sqrt(dx * dx + dy * dy)

    # 1. Discard draw position for each player
    numbers = data['number']
    for p in draw[0]:
        numbers.sort(key=lambda n: distance(n[1], p[1]))
        logging.debug("Discarding draw pos: {} - {}".format(numbers[0], p))
        del numbers[0]

    
    # 2. Find players for seeding or Q or WC or LL status

    # 2a. group potential seeds by number
    max_seed = len(draw[0]) / 2

    seedlist = data['seed'] + numbers
    seeds = { s: [] for s, pos in seedlist if int(s) <= max_seed}
    
    for s, pos in seedlist:
        if int(s) <= max_seed:
            seeds[s] += [pos]

    seeds = sorted(seeds.items(), key=lambda a: int(a[0]))

    logging.debug("Seeds available: {}".format(pprint.pformat(seeds)))

    status = { name: (None, None) for name, position in draw[0] 
            if name != "BYE"}

    players_flat = [p for l in draw for p in l if p[0] != "BYE"]

    # for each seed, find the matching player and vote
    last_seed = 0
    for s, poslist in seeds:

        candidates = {}
        for pos in poslist:
            player = min(players_flat, key=lambda p: distance2(pos, p[1]))
            if player[0] in candidates:
                candidates[player[0]] += 1
            else:
                candidates[player[0]] = 1
        vote = max(candidates.items(), key=lambda c: c[1])[0]
        if status[vote][0] is None:
            status[vote] = (s, None)

    # 2b. assign other status

    players_flat = [p for p in draw[0] if p[0] != "BYE"]
    for s, pos in data['status']:
        #players_flat.sort(key=lambda p: distance(pos, p[1]))
        p, pos = min(players_flat, key=lambda p: distance2(pos, p[1]))
        old_s, c = status[p]
        if old_s == None:
            status[p] = (s, c)
        else:
            status[p] = (old_s + "," + s, c)

        #for p, pos in players_flat:
            #if status[p][0] == None:
                #status[p] = (s, )
                #break

    # 3. Find country for each player
    for c, pos in data['country']:
        player = min(players_flat, key=lambda p: distance(pos, p[1]))[0]
        status[player] = (status[player][0], c)

    return status

def drawsheet_print_draw(draw, status):
    """
    Return a human readable representation of the drawsheet
    """
    y_top_skip = 0
    y_inner_skip = 1
    x = 8
    y = 0
    n = 0
    output = []
    for rnd in draw:
        y = y_top_skip

        if n == 0:
            for p in rnd:
                try:
                    s = status[p[0]]
                    if s[1] == None:
                        ctry = ''
                    else:
                        ctry = s[1]
                    if s[0] == None:
                        stat = ''
                    else:
                        stat = s[0]

                    p_out = "{:2} {} - {}".format(stat, p[0], ctry)
                except KeyError:
                    p_out = "   " + p[0]
                output += [p_out]
                output += ['']
        else:
            for p in rnd:
                comma_pos = p[0].find(',')
                if comma_pos == -1:
                    name = p[0]
                else:
                    name = p[0][:comma_pos + 3]
                
                output[y] = "{}{} ({})".format(' ' * x, name, p[2])

                y += y_inner_skip + 1

            x += 8 

        y_top_skip = y_inner_skip
        y_inner_skip = y_inner_skip * 2 + 1
        n+=1

    return '\n'.join(output)


def drawsheet_process(text, meta = None, qualifying = False):
    """
    Parse and process a drawsheet
    returns (draw, status, meta)
    """
    data, width = drawsheet_parse(text)

    logging.debug("################# POST-PROCESS DRAW ##################3")

    # get drawsize
    drawsize = len(data['fullname'])

    if not qualifying:
        # set to the next lowest power of 2
        # we just hope there aren't extra fullnames in qualies
        while drawsize & (drawsize - 1) != 0:
            drawsize = drawsize & (drawsize - 1)

    logging.debug("Physical Width: {}".format(width))
    logging.debug("Drawsize: {}".format(drawsize))

    # find the correnct x-values to use
    middle = width / 2
    left_count = 0
    right_count = 0
    for d in data['fullname']:
        ((x1, x2), y) = d[1]
        if (x1 + x2) / 2 < middle:
            left_count += 1
        else:
            right_count += 1

    logging.debug("Left Side: {} players".format(left_count))
    logging.debug("Right Side: {} players".format(right_count))

    # set the x value by page side
    # if they're about even, we're looking at a double-sided draw
    # otherwise, we use the left-hand value
    if left_count - right_count < 5:
        double_sided = True
        logging.debug("Doublesized: True")
    else:
        double_sided = False
        logging.debug("Doublesized: False")


    for k, datum in data.items():
        new_datum = []
        for d in datum:
            ((x1, x2), y) = d[1]
            if double_sided and (x1 + x2) / 2 > middle:
                new_datum += [(d[0], (x2, y))]
            else:
                new_datum += [(d[0], (x1, y))]
        data[k] = new_datum

    # divide base draw into columns
    def divide_into_columns(playerlist):
        columns = []
        for p in playerlist:
            x, y = p[1]
            if len(columns) == 0:
                # first column
                columns += [[[p], x]]
                continue
                
            added = False
            for column in columns:
                last, (last_x, last_y) = column[0][-1]
                if (abs(column[1] - x) < 15 
                        and abs(last_y - y) < 6):
                    column[0] += [p]
                    added = True
                    break

            if not added:
                # new column
                columns += [[[p], x]]

        return [c[0] for c in columns]

    columns = divide_into_columns(data['fullname'])

    logging.debug("################# COLUMNS ##################3")
    logging.debug(pprint.pformat(columns))
    
    # longer columns == earlier rounds, put them first
    columns.sort(key=lambda a: len(a), reverse=True)

    # find the players in the draw (i.e. first round)
    draw_base = []
    while len(draw_base) < drawsize:
        if columns == []:
            print("FAILED: not enough starting draw players found!")
            return 
        draw_base += columns[:1][0]
        del columns[:1]

    # get the rest of the player entries
    players = [p for c in columns for p in c]
    players += data['shortname']
    players += data['orderedname']

    # These represent wins by that player, organized by player
    wins = {}
    for p in players:
        name = p[0] 
        if name not in wins:
            wins[name] = []

        wins[name] += (p,)

    # Fill in the rest of the draw
    draw = [draw_base]
    drawsheet_complete_draw(draw, wins, data['score'])

    # scores that weren't used are numbers, add them 
    # one by one to the numbers list
    new_numbers = []
    for e in data['score']:
        l = e[0].split(' ')

        for i in range(len(l)):
            length = sum(len(a) + 1 for a in l[:i])
            new_numbers += [(l[i], (e[1][0] + length, e[1][1]))]

    data['score'] = []
    data['number'] += new_numbers

    # fill in status and country info
    status = drawsheet_players_status(draw, data)
    logging.debug("######## DRAW ########")
    logging.debug(pprint.pformat(draw))
    logging.debug("######## STATUS ########")
    logging.debug(pprint.pformat(status))

    # Ask the user to confirm the data
    
    if qualifying:
        review = input('Review qualifying draw? [Y/n]: ')
    else:
        review = input('Review draw? [Y/n]: ')

    if review not in ('N', 'n'):
        less = subprocess.Popen('less', stdin=subprocess.PIPE)
        less.communicate(bytes(
            drawsheet_print_draw(draw, status), 'UTF-8'))

    if not meta:
        meta = drawsheet_get_all_meta(data)

    return (draw, status, meta)
