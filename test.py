# pylint: skip-file
# pylint: enable=wrong-import-position
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tracex.tracex.settings")

from tracex.extraction.prototype import input_inquiry as ii
from tracex.extraction.prototype import input_handling as ih
from tracex.extraction.prototype import output_handling as oh
from tracex.extraction.prototype import utils as u
from tracex.extraction.prototype import function_calls as fc
from tracex.extraction.prototype import prompts as p
from tracex.extraction.prototype import create_xes as x

# text = open(u.input_path / "journey_synth_covid_0.txt").read()
# df = ih.convert_text_to_bulletpoints(text)
# print(df)
# df = ih.add_start_dates(text, df)
# df = ih.add_end_dates(text, df)
# df = ih.add_durations(df)
# # df = ih.add_event_types(df)
# # df = ih.add_locations(df)

# print(df)

# ih.convert_dataframe_to_csv(df)
x.create_xes(u.output_path / "single_trace.csv", "test", "event_information")

# output = 'The end date for the bulletpoint "Experiencing mild cough and fatigue" and the start date 20220108T0000 is 20230911T0000.'

# fc_message = [
#     {"role": "system", "content": p.END_DATE_CONTEXT},
#     {
#         "role": "user",
#         "content": p.END_DATE_FUNCTION_CALL
#         + "The text: "
#         + output
#     },
# ]


# print(u.query_gpt(fc_message, tool_choice={ "type": "function", "function": {"name": "add_end_dates"}}))
