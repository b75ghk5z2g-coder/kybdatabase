# 29 datasources from the OpenCorporates KYB collection.
# status: "loader" = implemented, "url" = downloadable available, "manual" = no public bulk download known
SOURCES = [
    {"id": "abuja-mou-psc",        "name": "Abuja MoU Port State Control Inspections",                "country": "Global",   "entities": 6348,    "status": "manual", "url": None},
    {"id": "blacksea-mou-psc",     "name": "Black Sea MoU Port State Control Inspections",            "country": "Global",   "entities": 8702,    "status": "manual", "url": None},
    {"id": "bosnia-registers",     "name": "Bosnia and Herzegovina Registers of businesses",          "country": "BA",       "entities": 196518,  "status": "manual", "url": None},
    {"id": "bic-reference",        "name": "Business Identifier Code (BIC) Reference Data",           "country": "Global",   "entities": 31750,   "status": "url",   "url": "https://www.swift.com/resource/..."},
    {"id": "uk-psc",               "name": "Companies House (UK) Persons with Significant Control",   "country": "GB",       "entities": 13988358,"status": "url",   "url": "https://download.companieshouse.gov.uk/en_pscs_data.html"},
    {"id": "cyprus-registry",      "name": "Cyprus company registry",                                 "country": "CY",       "entities": 1592357, "status": "manual", "url": None},
    {"id": "czech-register",       "name": "Czech Republic Business Register",                        "country": "CZ",       "entities": 4167756, "status": "url",   "url": "https://wwwinfo.mfcr.cz/ares/"},
    {"id": "germany-offenereg",    "name": "Deutsches Handelsregister (OffeneRegister.de)",           "country": "DE",       "entities": 9010326, "status": "url",   "url": "https://opendatacloud.de/"},
    {"id": "estonia-eregister",    "name": "Estonia e-Business Register (E-ariregister)",             "country": "EE",       "entities": 1114858, "status": "url",   "url": "https://avaandmed.eesti.ee/"},
    {"id": "eu-firds",             "name": "EU Financial Instruments Reference Data System (FIRDS)",  "country": "EU",       "entities": 5657088, "status": "url",   "url": "https://registers.esma.europa.eu/"},
    {"id": "georgia-registry",     "name": "Georgian Company Registry",                               "country": "GE",       "entities": 627037,  "status": "manual", "url": None},
    {"id": "gleif",                "name": "GLEIF Concatenated Data File",                           "country": "Global",   "entities": 12671471,"status": "loader", "url": "https://www.gleif.org/en/lei-data/gleif-concatenated-file/download-the-concatenated-file"},
    {"id": "icij-offshoreleaks",   "name": "ICIJ OffshoreLeaks",                                     "country": "Global",   "entities": 1614277, "status": "url",   "url": "https://offshoreleaks.icij.org/pages/database"},
    {"id": "kazakhstan-register",  "name": "Kazakhstan State Register of legal entities",            "country": "KZ",       "entities": 1422966, "status": "manual", "url": None},
    {"id": "latvia-uregister",     "name": "Register of Enterprises of the Republic of Latvia",      "country": "LV",       "entities": 869578,  "status": "url",   "url": "https://data.gov.lv/"},
    {"id": "ror",                  "name": "Research Organizations Registry",                        "country": "Global",   "entities": 137398,  "status": "loader", "url": "https://www.ror.org/"},
    {"id": "ru-egrul",             "name": "Russian Unified State Register of Legal Entities (EGRUL)","country": "RU",      "entities": 23876747,"status": "url",   "url": "https://egrul.nalog.ru/"},
    {"id": "sk-rpvs",              "name": "Slovakia Public Sector Partners Register (RPVS)",         "country": "SK",       "entities": 146246,  "status": "manual", "url": None},
    {"id": "moldova-register",     "name": "State Registers of Legal Entities (Moldova)",             "country": "MD",       "entities": 768709,  "status": "manual", "url": None},
    {"id": "tajikistan-register",  "name": "Tajikistan Unified State Register of taxpayers",          "country": "TJ",       "entities": 53082,   "status": "manual", "url": None},
    {"id": "tokyo-mou-psc",        "name": "Tokyo MoU Port State Control Inspections",                "country": "Global",   "entities": 26548,   "status": "manual", "url": None},
    {"id": "uk-firds",             "name": "UK Financial Instruments Reference Data System (FIRDS)",  "country": "GB",       "entities": 6248942, "status": "url",   "url": "https://registers.fca.org.uk/"},
    {"id": "ua-edr",               "name": "Ukraine Consolidated State Registry (EDR)",               "country": "UA",       "entities": 7241303, "status": "url",   "url": "https://edr.data.gov.ua/"},
    {"id": "us-corpwatch",         "name": "US CorpWatch EX-21 Filings",                              "country": "US",       "entities": 1421198, "status": "url",   "url": "http://www.corpwatch.org/"},   # noqa: E501
    {"id": "us-fatca-ffi",         "name": "US FATCA Foreign Financial Institution (FFI) List",       "country": "US",       "entities": 516298,  "status": "url",   "url": "https://www.irs.gov/businesses/corporations/fatca-list-of-ffis"},
    {"id": "us-fara",              "name": "US Foreign Agents Registration Act list",                 "country": "US",       "entities": 33527,   "status": "url",   "url": "https://efoia.fara.gov/"},   # noqa: E501
    {"id": "us-msb",               "name": "US Money Services Business Registrant List",              "country": "US",       "entities": 60216,   "status": "url",   "url": "https://www.fincen.gov/msb-registrant-search"},
    {"id": "us-npi",               "name": "US National Provider Identifier Registry",                "country": "US",       "entities": 9726865, "status": "url",   "url": "https://download.cms.gov/nppes/NPI_Files.html"},
    {"id": "us-ofac",              "name": "US OFAC Press Releases",                                  "country": "US",       "entities": 10294,   "status": "loader", "url": "https://www.treasury.gov/ofac/downloads/sdn.csv"},
]

BY_ID = {s["id"]: s for s in SOURCES}


def list_sources():
    for s in SOURCES:
        print(f"{'[x]' if s['status'] == 'loader' else '[ ]'} {s['id']:<24} {int(s['entities']):>10,}  {s['name']}")