from enum import Enum

class AccessLevel(str, Enum):
    Visitor = "Visitor"
    Employee = "Employee"
    Contractor = "Contractor"
    Security = "Security"
    Admin = "Admin"
    SuperAdmin = "SuperAdmin"

class StatusEnum(str, Enum):
    Active = "Active"
    Suspended = "Suspended"
    Terminated = "Terminated"

class CertBool(str, Enum):
    None_ = "0"
    Yes = "1"

class YearEnum(str, Enum):
    _2025 = "2025"; _2026 = "2026"; _2027 = "2027"; _2028 = "2028"; _2029 = "2029"
    _2030 = "2030"; _2031 = "2031"; _2032 = "2032"; _2033 = "2033"; _2034 = "2034"; _2035 = "2035"

class MonthEnum(str, Enum):
    Jan = "01"; Feb = "02"; Mar = "03"; Apr = "04"; May = "05"; Jun = "06"
    Jul = "07"; Aug = "08"; Sep = "09"; Oct = "10"; Nov = "11"; Dec = "12"

class DayEnum(str, Enum):
    _01="01"; _02="02"; _03="03"; _04="04"; _05="05"; _06="06"; _07="07"; _08="08"; _09="09"; _10="10"
    _11="11"; _12="12"; _13="13"; _14="14"; _15="15"; _16="16"; _17="17"; _18="18"; _19="19"; _20="20"
    _21="21"; _22="22"; _23="23"; _24="24"; _25="25"; _26="26"; _27="27"; _28="28"; _29="29"; _30="30"; _31="31"

# Helper lists for Swagger enum parameters
ACCESS_LEVEL_VALUES = [e.value for e in AccessLevel]
STATUS_VALUES = [e.value for e in StatusEnum]
CERTBOOL_VALUES = [e.value for e in CertBool]
YEAR_VALUES = [e.value for e in YearEnum]
MONTH_VALUES = [e.value for e in MonthEnum]
DAY_VALUES = [e.value for e in DayEnum]