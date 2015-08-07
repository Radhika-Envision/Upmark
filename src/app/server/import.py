import xlrd
import string
import model
import app
import os
from parse import *



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
            # print("function:", str(function))
            function_obj = parse_cell_title(str(function['title']))
            function_order = function_obj['order']
            function_title = function_obj['title']
            # print("function order:", function_order)
            # print("function title:", function_title)
            # print("function:", function)
            function_description = parse_description(scoring_sheet, function['row_num'], "empty")
            # print("function description:", function_description)

            f = model.Function()
            f.survey_id = s.id
            f.title = function_title
            f.seq = int(function_order) - 1
            f.description = function_description
            session.add(f)
            session.flush()

            process_row = [row for row in process_title_row if "{}.".format(function_order) in parse_text(row['title'])] 
            for process in process_row:
                process_obj = parse_cell_title(str(process['title']))
                if process_obj:
                    process_order = parse("{function}.{process}", str(process_obj['order']))['process']
                    process_title = process_obj['title']

                    # print("process order:", process_order)
                    # print("process title:", process_title)
                    process_description = parse_description(scoring_sheet, process['row_num'], "empty")
                    # print("process description:", process_description)

                    p = model.Process()
                    p.survey_id = s.id
                    p.function_id = f.id
                    p.title = process_title
                    p.seq = int(process_order) - 1
                    p.description = process_description
                    session.add(p)
                    session.flush()


                    subprocess_row = [row for row in subprocess_title_row if "{}.{}.".format(function_order, process_order) in str(row['title'])] 
                    for subprocess in subprocess_row:
                        subprocess_obj = parse_cell_title(str(subprocess['title']))
                        if subprocess_obj:
                            subprocess_order = parse("{function}.{process}.{subprocess}", str(subprocess_obj['order']))['subprocess']
                            subprocess_title = subprocess_obj['title']

                            # print("subprocess order:", subprocess_order)
                            # print("subprocess title:", subprocess_title)
                            subprocess_description = parse_description(scoring_sheet, subprocess['row_num'], "empty")
                            # print("subprocess description:", subprocess_description)

                            sp = model.Subprocess()
                            sp.survey_id = s.id
                            sp.process_id = p.id
                            sp.title = subprocess_title
                            sp.seq = int(subprocess_order) - 1
                            sp.description = subprocess_description
                            session.add(sp)
                            session.flush()

                            # for row in all_rows:
                            #     print("row", row[col2num("F")])
                            measure_title_row = [{"title" : row[col2num("k")], "row_num" : all_rows.index(row), "weight" : row[col2num("L")]} 
                                                for row in all_rows 
                                                if float(function_order) == parse_cell_number(row[col2num("C")]) and 
                                                float(process_order) == parse_cell_number(row[col2num("D")]) and
                                                float(subprocess_order) == parse_cell_number(row[col2num("E")]) and
                                                parse_cell_number(str(row[col2num("F")])) != 0 and
                                                parse_cell_number(str(row[col2num("G")])) == 1] 


                            for measure in measure_title_row:
                                measure_obj = parse_cell_title(str(measure['title']))
                                if measure_obj:
                                    measure_order = parse("{function}.{process}.{subprocess}.{measure}", str(measure_obj['order']))['measure']
                                    measure_title = measure_obj['title']

                                    # print("measure order:", measure_order)
                                    # print("measure title:", measure_title)
                                    # print("measure row_num:",  measure['row_num'])

                                    measure_intent = parse_description(scoring_sheet, measure['row_num'], "Intent")
                                    measure_inputs = parse_description(scoring_sheet, measure['row_num'] + 1, "Iputs")
                                    measure_scenario = parse_description(scoring_sheet, measure['row_num'] + 2, "Scenario")
                                    measure_questions = parse_description(scoring_sheet, measure['row_num'] + 3, "Questions")
                                    measure_comments = parse_description(scoring_sheet, measure['row_num'] + 4, "Comments")
                                    measure_weight = parse_cell_number(measure['weight'])

                                    # print("measure measure_intent:", json.dumps(measure_intent))
                                    # print("measure measure_inputs:", measure_inputs)
                                    # print("measure measure_scenario:", measure_scenario)
                                    # print("measure measure_questions:", measure_questions)
                                    # print("measure measure_comments:", measure_comments)

                                    m = model.Measure()
                                    m.survey_id = s.id
                                    m.subprocess_id = sp.id
                                    m.seq = int(measure_order) - 1
                                    m.title = measure_title
                                    m.weight = measure_weight
                                    m.intent = measure_intent
                                    m.inputs = measure_inputs
                                    m.scenario = measure_scenario
                                    m.questions = measure_questions
                                    m.response_type = "Test"
                                    session.add(m)
                                    session.flush()




def parse_description(sheet, starting_row_num, prev_column):
    print("starting_row_num", starting_row_num, "sheet", sheet.nrows)
    if starting_row_num + 1 >= sheet.nrows:
        return ""

    header_cell = str(sheet.cell(starting_row_num + 1, col2num("J")))
    desc = ""
    if prev_column in str(header_cell):
        description_cell = sheet.cell(starting_row_num + 1, col2num("K"))
        # if prev_column == "Comments":
        desc = parse_text(description_cell)
        desc += parse_description(sheet, starting_row_num + 1, prev_column)
        return desc
    else:
        return ''


def parse_cell_title(row_text):
    return parse("{order} - {title}", parse_text(row_text))

def parse_text(row_text):
    row_text = str(row_text)
    if row_text[:6] == "text:'":
        parse_obj = parse("text:'{text}'", row_text)
    else:
        parse_obj = parse('text:"{text}"', row_text)
    if parse_obj:
        return parse_obj['text']
    return ''


def parse_cell_number(cell):
    value_obj = parse("number:{value}", str(cell))
    if value_obj is None:
        return 0
    return float(value_obj['value'])


#----------------------------------------------------------------------
if __name__ == "__main__":
    path = "../importer/sample.xls"
    open_file(path)