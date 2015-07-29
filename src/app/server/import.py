import xlrd
import string
from parse import *
import model
import app
import os

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
    scoring_sheet = book.sheet_by_name("Scoring")

    # # read rows
    all_rows = []
    for row_num in range(0, scoring_sheet.nrows - 1):
        cell = scoring_sheet.row(row_num)
        all_rows.append(cell)
        filter =  scoring_sheet.cell(row_num, col2num("S"))
        #print("filter:", filter)
        # print("cell:" , cell)
    
    model.connect_db(os.environ.get('DATABASE_URL'))
    
    with model.session_scope() as session:
        s = model.Survey()
        s.title = "test1"
        session.add(s)
        session.flush()

        function_title_row = [{"title" : row[col2num("J")], "row_num" : all_rows.index(row)} for row in all_rows if "'Function Header" in str(row[col2num("S")])]
        process_title_row = [{"title" : row[col2num("J")], "row_num" : all_rows.index(row)} for row in all_rows if "'Process Header" in str(row[col2num("S")])]
        subprocess_title_row = [{"title" : row[col2num("J")], "row_num" : all_rows.index(row)} for row in all_rows if "'SubProcess Header" in str(row[col2num("S")])]
        #function_row = [row for row in all_rows]
        for function in function_title_row:
            #print("function:", str(function))
            function_obj = parse("text:'{order} - {title}'", str(function['title']))
            function_order = function_obj['order']
            function_title = function_obj['title']
            print("function order:", function_order)
            print("function title:", function_title)
            print("function:", function)
            function_description = parse_description(str(scoring_sheet.cell(function['row_num'] + 1, col2num("K"))))
            print("function description:", function_description)

            f = model.Function()
            f.survey_id = s.id
            f.title = function_title
            f.seq = int(function_order) - 1
            f.description = function_description
            session.add(f)
            session.flush()

            process_row = [row for row in process_title_row if str(function_order) + "." in str(row['title'])] 
            for process in process_row:
                process_obj = parse("text:'{order} - {title}'", str(process['title']))
                if process_obj:
                    process_order = parse("{function}.{process}", str(process_obj['order']))['process']
                    process_title = process_obj['title']

                    print("process order:", process_order)
                    print("process title:", process_title)
                    process_description = parse_description(str(scoring_sheet.cell(process['row_num'] + 1, col2num("K"))))
                    print("process description:", process_description)

                    p = model.Process()
                    p.survey_id = s.id
                    p.function_id = f.id
                    p.title = process_title
                    p.seq = int(process_order) - 1
                    p.description = process_description
                    session.add(p)
                    session.flush()


                    subprocess_row = [row for row in subprocess_title_row if str(function_order) + "." + str(process_order) + "." in str(row['title'])] 
                    for subprocess in subprocess_row:
                        subprocess_obj = parse("text:'{order} - {title}'", str(subprocess['title']))
                        if subprocess_obj:
                            subprocess_order = parse("{function}.{process}.{subprocess}", str(subprocess_obj['order']))['subprocess']
                            subprocess_title = subprocess_obj['title']

                            print("subprocess order:", subprocess_order)
                            print("subprocess title:", subprocess_title)
                            subprocess_description = parse_description(str(scoring_sheet.cell(subprocess['row_num'] + 1, col2num("K"))))
                            print("subprocess description:", scoring_sheet.cell(subprocess['row_num'] + 1, col2num("K")))

                            sp = model.Subprocess()
                            sp.survey_id = s.id
                            sp.process_id = p.id
                            sp.title = subprocess_title
                            sp.seq = int(subprocess_order) - 1
                            sp.description = subprocess_description
                            session.add(sp)
                            session.flush()



def parse_description(desc):
    if "text:'" in desc:
        return parse("text:'{desc}'", desc)['desc']
    else:
        return parse('text:"{desc}"', desc)['desc']

#----------------------------------------------------------------------
if __name__ == "__main__":
    path = "../importer/sample.xls"
    open_file(path)