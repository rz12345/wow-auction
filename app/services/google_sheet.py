from google.oauth2.service_account import Credentials
import gspread
import pandas as pd

class GoogleSheet:
    
    def __init__(self, sheet_url, worksheet_name):
        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file("app/configs/google-auth.json", scopes=scope)
        gs = gspread.authorize(creds)
        sheet = gs.open_by_url(sheet_url)
        self.worksheet = sheet.worksheet(worksheet_name)

    def getData(self):
        df = pd.DataFrame(self.worksheet.get_all_records())
        return df
    
    def addRow(self, list_data):
        return self.worksheet.append_row(list_data, table_range='A1')
    
    def addRows(self, list_data):
        return self.worksheet.append_rows(list_data, table_range='A1')
    
    def getColumnVals(self, col_idx):
        return self.worksheet.col_values(col_idx)
    