from smtplib import SMTP, SMTPSenderRefused
from email.message import EmailMessage
from csv import DictReader
from getpass import getpass
from pathlib import Path
import yaml
import time
import random
import re

RESSOURCES_PATH = Path.cwd() / 'ressources'
CONFIG_PATH = RESSOURCES_PATH / "config.yml"

def get_config(config_path):
    """returns the configuration file in a dict"""
    with open(config_path) as cfg:
        config = yaml.safe_load(cfg)
    return config


def list_variables(string):
    """returns a list of all variables of the form '{var}' inside the string given"""

    regex = r'\{([^{}]*)\}'
    return set(re.findall(regex, string))

def replace_placeholders(string, variables):
    """replaces all the variables in the string of the form '{var}' with 
    their values given in the dictionary 'variables'"""

    return string.format_map(variables)

def fill_variables(string, variables):
    """replaces all the variables in the string by their values in the 'variables' dict
    accepts that the dict contains more variables and ensures that if there is one variable in the string
    and not in the dict then an error is thrown"""

    used_vars = list_variables(string)
    vars = {key: value for key, value in variables.items() if key in used_vars}
    return replace_placeholders(string, vars)

def fill_placeholders(email_parts, variables, expressions):
    """fills all the placeholders of the form {Placeholder} in all the email parts by their respective 
    variables or expressions"""

    expr = {k: eval((fill_variables(v, variables))) for k, v in expressions.items()}
    variables.update(expr)
    return {key: fill_variables(value, variables) for key, value in email_parts.items()}

def build_mail(pdf, pdf_name, signature, raw_template):
    """builds an Email object given a pdf, a signature and a template"""

    msg = EmailMessage()
    body = raw_template['Body']

    for key, value in raw_template.items():
        if key == "Body":
            continue
        msg[key] = value
    msg.set_content(body.replace('\n', '\n\n'))
    msg.add_attachment(pdf, maintype='application', subtype='pdf', filename=pdf_name)
    
    text = msg.get_body()
    text.add_alternative(html_body(body, signature), subtype="html")
    return msg

def html_body(body, signature):
    """builds the html body for a mail and inserts the signature at the end of the mail"""

    html = f"""\
        <html>
            <head></head>
            <body>
                <p style="font-family: Arial, sans-serif; font-size: 15px;">
                    {body.replace('\n', '<br>' * 2)}
                </p>
            </body>
            <footer>{signature}</footer>
        </html>
        """
    return html

def read_file(path, mode='r'):
    """reads a file and outputs all it's content"""

    with open(path, mode) as file:
        return file.read()

def parse_template(template_path):
    """given the path to a template parses it to build all the sections 
    that will be used to construct an Email, the placeholders are not filled"""

    email_parts = {
        'From'          : '',
        'To'            : '',
        'Cc'            : '',
        'Subject'       : '',
        'Body'          : ''
    }
    current_part = None
    expressions = {}
    with open(template_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line.startswith('#'):
                continue
            if line.startswith('<Expressions>'):
                expr = line[13:].split(';')
                expr_name = expr[0].strip()
                expr_value = expr[1].strip()
                expressions[expr_name] = expr_value
            elif line.startswith('<From>'):
                current_part = 'From'
                email_parts[current_part] = line[6:].strip()
            elif line.startswith('<To>'):
                current_part = 'To'
                email_parts[current_part] = line[4:].strip()
            elif line.startswith('<Cc>'):
                current_part = 'Cc'
                email_parts[current_part] = line[4:].strip()
            elif line.startswith('<Subject>'):
                current_part = 'Subject'
                email_parts[current_part] = line[9:].strip()
            elif line.startswith('<Body>'):
                current_part = 'Body'
                continue
            elif current_part == 'Body':
                email_parts[current_part] += line + '\n'
    return email_parts, expressions

def get_csv_data(csv_path):
    """returns a list of dictionaries that contain a mapping from the category name to the value per line
    given the path to a csv"""

    with open(csv_path, 'r') as data:
        reader = DictReader(data)
        csv_data = [row for row in reader]
    return csv_data

def main():
    """builds emails from a template, a signature, a csv and a joint file and sends them 
    to all the people on the CSV"""
    
    config = get_config(CONFIG_PATH)
    email_parts, expressions = parse_template(RESSOURCES_PATH / config['general']['template'])
    signature = read_file(RESSOURCES_PATH / config['general']['signature'])
    pdf = read_file(RESSOURCES_PATH / config['general']['pdf'], mode='rb')
    pdf_name = config['general']['pdf_name'] 
    csv_data = get_csv_data(RESSOURCES_PATH / config['general']['csv'])

    server = {'host': config['server']['host'], 'port': config['server']['port']}
    login = {'user': config['server']['sender'], 'password': getpass("password: ")}
    print(server)

    emails = []
    for vars in csv_data:
        email_filled = fill_placeholders(email_parts, vars, expressions)
        emails.append(build_mail(pdf, pdf_name, signature, email_filled))
    
    with SMTP(config['server']['host'], config['server']['port']) as smtp:
        smtp.starttls()
        smtp.login(**login)
        i = 1
        for msg in emails:
            try:
                smtp.send_message(msg)
                print()
                print(f"{i} Emails sent")
                i += 1
                mean = config['general']['time_between_mails']  
                variance = config['general']['variance_between_mails']
                sleep_time = random.uniform(mean - variance, mean + variance)
                time.sleep(sleep_time)
            except SMTPSenderRefused as e:
                smtp.connect(**server)
                smtp.login(**login)
                smtp.send_message(msg)
                print()
                print(f"{i} Emails sent")
                i += 1
                mean = config['general']['time_between_mails']  
                variance = config['general']['variance_between_mails']
                sleep_time = random.uniform(mean - variance, mean + variance)
                time.sleep(sleep_time)
            except e:
                print("an unexpected error happened", e, sep='\n')
                return
main()
