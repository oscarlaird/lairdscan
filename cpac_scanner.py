#%%
import requests
import json

# Endpoint URL
url = 'http://production.data.conservative.org/v1/graphql'

# Request Headers
headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Referer': 'http://ratings.conservative.org/',
    'content-type': 'application/json',
    'x-hasura-user-id': '-1',
    'x-hasura-role': 'anonymous',
    'Origin': 'http://ratings.conservative.org',
    'Connection': 'keep-alive',
    'Priority': 'u=4',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
    'Content-Length': '1976'
}

# GraphQL query and variables
payload = {
    "operationName": "findPeople",
    "variables": {
        "limit": 1000,
        "search": None,
        "year": 2023,
        "district": None,
        "ordering": "lifetimeRating",
        "direction": "DESC",
        "from": "SC",
        "state": None
    },
    "query": """
    query findPeople($state: String, $district: String, $limit: Int = 10, $search: String, $year: Int, $party: String, $chamber: String, $from: String, $ordering: String, $direction: String, $minRating: float8, $maxRating: float8) {
        count: ratings_searchPeopleCount2(args: {search: $search, year: $year, chamber: $chamber, party: $party, district: $district, state: $state, from: $from, minRating: $minRating, maxRating: $maxRating}) {
            count
            __typename
        }
        ratings_people: ratings_searchPeople2(args: {search: $search, year: $year, chamber: $chamber, party: $party, district: $district, state: $state, from: $from, limit: $limit, ordering: $ordering, direction: $direction, minRating: $minRating, maxRating: $maxRating}) {
            id
            name
            firstName
            middleName
            lastName
            imageUrl
            thumbnailUrl
            lifetimeRating
            yearsRated: acuRatings_aggregate(where: {rating: {_is_null: false}}) {
                aggregate {
                    count
                    __typename
                }
                __typename
            }
            history(where: {year: {_eq: $year}}, order_by: {year: desc_nulls_last}, limit: 2) {
                party
                chamber
                district
                year
                from
                state
                __typename
            }
            acuRatings(where: {year: {_lte: $year}, rating: {_is_null: false}}, order_by: {year: desc_nulls_last}, limit: 2) {
                rating
                year
                __typename
            }
            acuLifetimeRatings(where: {year: {_lte: $year}, rating: {_is_null: false}}, order_by: {year: desc_nulls_last}, limit: 2) {
                rating
                year
                __typename
            }
            voteCounts(where: {year: {_eq: $year}}) {
                count
                year
                __typename
            }
            sponsorCounts(where: {year: {_eq: $year}}, limit: 0) {
                count
                year
                __typename
            }
            __typename
        }
    }
    """
}

# Send the request
response = requests.post(url, headers=headers, json=payload)

# Log the response
print("Status Code:", response.status_code)
print("Response Text:", response.text)
