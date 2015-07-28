import xlrd
import string

def col2num(col):
    num = 0
    for c in col:
        if c in string.ascii_letters:
            num = num * 26 + (ord(c.upper()) - ord('A'))
    return num

#----------------------------------------------------------------------
def open_file(path):
    """
    Open and read an Excel file
    """
    book = xlrd.open_workbook(path)

    # print number of sheets
    print("nsheets: " , book.nsheets)

    # print sheet names
    print("book.sheet_names: ", book.sheet_names())

    # get the first worksheet
    scoring_sheet = book.sheet_by_name("Scoring")

    # # read a row
    print("scoring_sheet.nrows: ", scoring_sheet.nrows)
    #for row in scoring_sheet.row_values:
    #    print("row: %s", row)

    # # read a cell
    all_rows = []
    for row_num in range(0, scoring_sheet.nrows):
        cell = scoring_sheet.row(row_num)
        all_rows.append(cell)
        filter =  scoring_sheet.cell(row_num, col2num("S"))
        #print("filter:", filter)
        # print("cell:" , cell)
    
    function_row = [row for row in all_rows if row[col2num("S")] == "text:'Function Header'"]
    #function_row = [row for row in all_rows]
    for function in function_row:
        print("function:", function)

    # # read a row slice
    # print("first_sheet: %s", first_sheet.row_slice(rowx=0,
    #                             start_colx=0,
    #                             end_colx=2))

#----------------------------------------------------------------------
if __name__ == "__main__":
    path = "sample.xls"
    open_file(path)