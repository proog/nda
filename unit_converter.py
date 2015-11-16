import re
import http
import http.client


def extract_unit(string):
    left_units = ['\$','£','€']
    right_units = ['\'','"','ft','foot','feet','inch','inches','m','meter','meters','metres','cm','mm']

    pattern = r'^.*?(\d+(\.\d+)?)\s*(' + '|'.join(right_units) + ')(\s+|$).*'
    m = re.match(pattern, string.lower())

    if m is not None and len(m.groups()) == 4:
        return float(m.group(1)), m.group(3)
    return None, None


def contains_unit(string):
    return extract_unit(string) is not None


def convert_unit(string):
    feet = (lambda x: x * 0.3048), 'm'
    inches = (lambda x: x * 2.54), 'cm'
    meters = (lambda x: x / 0.3048), 'ft'
    cm = (lambda x: x / 2.54), 'inches'
    mm = (lambda x: x / 25.4), 'inches'

    conversions = {
        '\'': feet,
        'ft': feet,
        'foot': feet,
        'feet': feet,
        '"': inches,
        'inch': inches,
        'inches': inches,
        'm': meters,
        'metres': meters,
        'meters': meters,
        'cm': cm,
        'mm': mm
    }

    value, unit = extract_unit(string)

    if unit is not None and unit in conversions:
        return conversions[unit][0](value), conversions[unit][1]
    return None
