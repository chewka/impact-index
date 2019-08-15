# Collect data at the company-level using the Crunchbase API, USPTO API, and by scraping Wikipedia

import numpy as np
import pandas as pd
import datetime
from time import time as now
import math
import requests
import json
import os
from urllib.error import HTTPError
import copy

IRM_DIR = '../data/interim/'
PRC_DIR = '../data/processed/'
MAP_DIR = '../data/mappings/'

# # TAKE OUT
# company_df = pd.read_csv(IRM_DIR + 'company_df.csv', index_col=0)
# company_df = company_df.drop(company_df[company_df.company_name == 'Yellow'].index).reset_index(drop=True)
# company_df = company_df.drop(company_df[company_df.company_name == 'Sesepei.com'].index).reset_index(drop=True)
# company_df = company_df.drop(company_df[company_df.company_name == 'Doublelinx'].index).reset_index(drop=True)

company_df = pd.read_csv(PRC_DIR + 'processed_company_df.csv', index_col=0)


def get_patents(company_row):
    """
    Function that sends an API request to the
    USPTO API to get the number of patents for
    a particular company, returning the patent
    count.
    """
    patents = 0
    company = company_row['company_name']
    confidences = []
    # print(company)

    # Make a get request
    response = requests.get('http://www.patentsview.org/api/assignees/query?q=' +
                            '{"_begins":{"assignee_organization":"' + str(company) + '"}}' +
                            '&f=["assignee_organization","patent_number","app_date",' +
                            '"patent_date","location_city","location_state"]')

    # Jsonify response
    try:
        parsed = json.loads(response.content)
    except ValueError:
        print(company_row['company_name'], 'ERROR')
        return
    # How many assignees?
    try:
        count = parsed['count']
    except KeyError:
        return patents

    # If there's no patents
    if count == 0:
        return patents
    else:
        for assignee_pkg in parsed['assignees']:
            ########
            locations = assignee_pkg['locations']
            if len(locations) > 1:
                print('ALERT: Multiple locations')
                print(locations)

            # Get patent information
            patent_city = assignee_pkg['locations'][0]['location_city']
            patent_pkg = assignee_pkg['patents']
            # For each patent
            for p in patent_pkg:
                patent_date = p['patent_date']
                # Check validity of patent
                validity, confidence = check_validity(
                    company_city=company_row['city'],
                    founding_date=company_row['founding_date'],
                    closing_date=company_row['closing_date'],
                    patent_date=patent_date,
                    patent_city=patent_city
                )
                if validity:
                    patents += 1
                    confidences.append(confidence)

    if len(confidences) > 0:
        return patents, np.round(np.mean(confidences), 2)
    else:
        return patents, None


def check_validity(company_city, founding_date, closing_date,
                   patent_date, patent_city=None):
    """
    Function that checks whether a given patent
    application is within the dates of a company's
    life, and if the cities match (if the city of
    the patent application is provided).
    """
    # Convert strings to datetime type
    founding_date = datetime.datetime.strptime(founding_date, '%Y-%m-%d')
    patent_date = datetime.datetime.strptime(patent_date, '%Y-%m-%d')

    try:
        # If closing date is null, company is still running
        if math.isnan(closing_date):
            # Check founding date vs. patent(s)
            if patent_date < founding_date:
                return False, 0
            else:
                # Check city if it exists
                if patent_city:
                    if company_city == patent_city:
                        return True, 2
                    return False, 0
                return True, 1
    # If company has closed (TypeError occurs if closing_date is not NaN)
    except TypeError:
        closing_date = datetime.datetime.strptime(closing_date, '%Y-%m-%d')
        # Check if patent app date is within dates of company's life
        if founding_date < patent_date < closing_date:
            # Check city if it exists
            if patent_city:
                if company_city == patent_city:
                    return True, 2
                else:
                    return False, 0
            else:
                return True, 1
        else:
            return False, 0


def get_wiki_jobs(company_name):
    name = company_name.replace(' ', '_')
    url = 'https://en.wikipedia.org/wiki/' + name
    num_employees = 0
    try:
        try:
            dfs = pd.read_html(url)
            # If dfs are found, get the first one with len > 5
            if len(dfs) > 0:
                check = False
                num_dfs = len(dfs)
                for i in range(num_dfs):
                    if check == False:
                        df = dfs[i]
                        if len(df) > 5:
                            check = True
                # Make sure first column is equal to 0, otherwise it's not a df we're interested in
                if df.columns[0] == 0:
                    try:
                        # Make sure first column is a string
                        df.iloc[:, 0] = df.iloc[:, 0].astype(str)
                        # Lowercase it
                        df.iloc[:, 0] = df.iloc[:, 0].str.lower()
                        # If 'employees' is in the first column...
                        if df.iloc[:, 0].str.contains('employees').any():
                            num_employees = df.loc[df[0].str.contains('employees', case=False, na=False)][1].values[0]
                        elif df.iloc[:, 0].str.contains('staff').any():
                            num_employees = df.loc[df[0].str.contains('staff', case=False, na=False)][1].values[0]
                    except UnboundLocalError:
                        pass

            return num_employees

        except ValueError:
            return num_employees

    except HTTPError:
        return num_employees


def string_to_int(num_employees_string):
    """
    Function that takes in various incorrectly formatted
    strings and gets the number of employees from it,
    returning an integer.
    """
    # Make copy of original string
    og_copy = copy.deepcopy(num_employees_string)

    # Check if it's nan
    if str(num_employees_string) == 'nan':
        return 0

    # Lowercase the string
    num_employees_string = num_employees_string.lower()

    # If 'worldwide' in string, or the string is very long, we don't want it
    if ('worldwide' in num_employees_string) or (len(num_employees_string) > 50):
        return 0

    # Replace k with thousands
    for each in [
        '1k',
        '2k',
        '3k',
        '4k',
        '5k',
        '6k',
        '7k',
        '8k',
        '9k',
    ]:
        if each in num_employees_string:
            new = each.replace('k', '000')
            num_employees_string = num_employees_string.replace(each, new)

    # Replace certain characters with nothing
    for each in [
        ',',
        '~',
        '≈',
        '+',
        '"',
        '>',
        '<',
        '/',
        'over ',
        'approx. ',
        'approximately ',
        'ca. ',
        'est. ',
        '-plus',
        'more than ',
        'below ',
        'total: ',
        'about ',
        'c. ',
        'nearly ',
        'appr. ',
        'circa',
        '.',
    ]:
        if each in num_employees_string:
            num_employees_string = num_employees_string.replace(each, '')

    # If there is a leading space, get rid of it
    if num_employees_string[0] == ' ':
        num_employees_string = num_employees_string[1:]

    # If left bracket, replace with space bracket
    if '[' in num_employees_string:
        num_employees_string = num_employees_string.replace('[', ' [')

    # If left parenthesis, replace with space parenthesis
    if '(' in num_employees_string:
        num_employees_string = num_employees_string.replace('(', ' (')

    # Split on first space
    num_employees_string = num_employees_string.split(' ')[0]

    # If range with '-' (short or long), get average (do this last as others have dashes in them)
    for dash in ['-', '–']:
        if dash in str(num_employees_string):
            first = int(num_employees_string.split(dash)[0])
            second = int(num_employees_string.split(dash)[1])
            num_employees_string = round((first + second) / 2)

    try:
        num_employees_string = int(num_employees_string)
    except ValueError:
        print(f'Error encountered for {num_employees_string} (original: {og_copy}, ' +
              f'type: {type(num_employees_string)})')
        return 0

    return int(num_employees_string)


def get_employee_count(company_name, i, verbose=False):
    """
    Function that scrapes the employee count, if it exists,
    from the specified company's Wikipedia page.
    """
    num_employees = get_wiki_jobs(company_name)
    try:
        num_employees = int(num_employees)
    # If it's a string, use helper function
    except ValueError:
        num_employees = string_to_int(num_employees)

    # Print info if specified
    if verbose:
        if num_employees > 0:
            print(f'[{i}] - {num_employees} jobs for {company_name}')

    return num_employees


def main():
    """
    Function that:
        1. collects patent data from the USPTO API and validates
           it based on city and date
        2. validates jobs created data by scraping Wikipedia
    """
    companies_to_exclude = []

    # # Check if mapping exists in directory
    # if os.path.isfile(IRM_DIR + 'PATENT_MAPPING.json'):
    #     # Load mappings if they exists
    #     with open(IRM_DIR + 'PATENT_MAPPING.json') as json_file:
    #         PATENT_MAPPING = json.load(json_file)
    #     with open(IRM_DIR + 'PATENT_CONF_MAPPING.json') as json_file:
    #         PATENT_CONF_MAPPING = json.load(json_file)
    # # If they doesn't exist, make them
    # else:
    #     PATENT_MAPPING = {}
    #     PATENT_CONF_MAPPING = {}
    #
    # # Collect and validate patent data
    # checkpoints = [
    #     1000, 5000, 10000, 20000, 30000, 40000, 50000, 60000,
    #     70000, 80000, 90000, 100000, 110000, 120000, 130000,
    #     140000, 150000, 160000
    # ]
    # print('Collecting patents...')
    # t0 = now()
    # for i in company_df.index:
    #     if i in checkpoints:
    #         print('-----------------------------------------------------')
    #         print('Checkpoint: {}/{}'.format(i, company_df.shape[0]))
    #         print('-----------------------------------------------------')
    #         # Save patent mappings
    #         with open(IRM_DIR + 'PATENT_MAPPING.json', 'w') as f:
    #             json.dump(PATENT_MAPPING, f, sort_keys=True, indent=4)
    #         with open(IRM_DIR + 'PATENT_CONF_MAPPING.json', 'w') as f:
    #             json.dump(PATENT_CONF_MAPPING, f, sort_keys=True, indent=4)
    #     if company_df.at[i, 'permalink'] not in PATENT_MAPPING.keys():
    #         # If company name is not null
    #         try:
    #             patents, confidence = get_patents(company_df.iloc[i])
    #             if patents > 0:
    #                 company = company_df.at[i, 'company_name']
    #                 print(
    #                     f'{company}' + '.'*(36-len(company)) + '{:,} patent(s) total, c={}'.format(
    #                         patents,
    #                         confidence
    #                     ))
    #             company_df.at[i, 'patents'] = patents
    #             company_df.at[i, 'patent_confidence'] = confidence
    #             PATENT_MAPPING[company_df.at[i, 'permalink']] = patents
    #             PATENT_CONF_MAPPING[company_df.at[i, 'permalink']] = confidence
    #         except TypeError:
    #             companies_to_exclude.append(company_df.iloc[i]['permalink'])
    # t_patents = now() - t0
    #
    # print(f'Took {int(np.round(t_patents))} seconds to collect patents for all companies.')
    #
    # # Save patent mappings
    # with open(IRM_DIR + 'PATENT_MAPPING.json', 'w') as f:
    #     json.dump(PATENT_MAPPING, f, sort_keys=True, indent=4)
    # with open(IRM_DIR + 'PATENT_CONF_MAPPING.json', 'w') as f:
    #     json.dump(PATENT_CONF_MAPPING, f, sort_keys=True, indent=4)
    #
    # # Save data to csv
    # company_df.to_csv(IRM_DIR + 'company_df_main.csv')

    # Validate jobs created data using Wikipedia

    # Check if mapping exists in directory
    if os.path.isfile(MAP_DIR + 'WIKI_JOBS_MAPPING.json'):
        # Load mapping if it exists
        with open(MAP_DIR + 'WIKI_JOBS_MAPPING.json') as json_file:
            WIKI_JOBS_MAPPING = json.load(json_file)
    # If it doesn't exist, make it
    else:
        WIKI_JOBS_MAPPING = {}

    print('Collecting jobs data from Wikipedia...')
    t0 = now()
    for i in company_df.index[32000:]:
        if (i % 2000 == 0) & (i != 0):
            print('------------------------------------------------')
            print('Checkpoint: {}/{}'.format(i, company_df.shape[0]))
            print('------------------------------------------------')
            # Save jobs mapping
            with open(MAP_DIR + 'WIKI_JOBS_MAPPING.json', 'w') as f:
                json.dump(WIKI_JOBS_MAPPING, f, sort_keys=True, indent=4)
        if company_df.at[i, 'permalink'] not in WIKI_JOBS_MAPPING.keys():
            company_name = company_df.at[i, 'company_name']
            jobs = get_employee_count(company_name, i, verbose=True)
            # If company is closed, Wiki marks it as 0 jobs; in this case we want the Crunchbase number
            if jobs != 0:
                company_df.at[i, 'jobs_created'] = jobs
                # Add to mapping if it's not 0 jobs
                WIKI_JOBS_MAPPING[company_df.at[i, 'permalink']] = jobs
    t_jobs = now() - t0

    print(
        f'Took {int(np.round(t_jobs))} seconds to collect job data from Wikipedia on {company_df.shape[0]} companies.'
    )

    # Save jobs mapping
    with open(MAP_DIR + 'WIKI_JOBS_MAPPING.json', 'w') as f:
        json.dump(WIKI_JOBS_MAPPING, f, sort_keys=True, indent=4)

    # Save data to csv
    company_df.to_csv(PRC_DIR + 'processed_company_df_main.csv')


if __name__ == '__main__':
    main()
