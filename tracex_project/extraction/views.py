"""This file contains the views for the extraction app.
Some unused imports and variables have to be made because of architectural requirement."""
# pylint: disable=unused-argument, unused-variable
import zipfile
import os
from tempfile import NamedTemporaryFile
import pm4py
import pandas as pd


from django.urls import reverse_lazy
from django.views import generic, View
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import redirect

from tracex.logic import utils
from extraction.forms import (
    JourneyUploadForm,
    ResultForm,
    FilterForm,
    JourneySelectForm,
)
from extraction.logic.orchestrator import Orchestrator, ExtractionConfiguration
from extraction.models import PatientJourney


# necessary due to Windows error. see information for your os here:
# https://stackoverflow.com/questions/35064304/runtimeerror-make-sure-the-graphviz-executables-are-on-your-systems-path-aft
os.environ["PATH"] += os.pathsep + "C:/Program Files/Graphviz/bin/"

IS_TEST = False  # Controls the presentation mode of the pipeline, set to False if you want to run the pipeline


class JourneyInputSelectView(generic.TemplateView):
    """View for choosing if you want to upload a patient journey or select from the database."""

    template_name = "choose_input_method.html"


class JourneyUploadView(generic.CreateView):
    """View for uploading a patient journey."""

    form_class = JourneyUploadForm
    template_name = "upload_journey.html"

    def form_valid(self, form):
        """Save the uploaded journey in the cache."""
        uploaded_file = self.request.FILES.get("file")
        content = uploaded_file.read().decode("utf-8")
        form.instance.patient_journey = content
        response = super().form_valid(form)

        return response

    def get_success_url(self):
        """Return the success URL."""

        return reverse_lazy("journey_details", kwargs={"pk": self.object.id})


class JourneySelectView(generic.FormView):
    """View for selecting a patient journey from the database."""

    model = PatientJourney
    form_class = JourneySelectForm
    template_name = "select_journey.html"
    success_url = reverse_lazy("journey_details")

    def form_valid(self, form):
        """Pass selected journey to orchestrator."""
        selected_journey = form.cleaned_data["selected_patient_journey"]
        patient_journey_entry = PatientJourney.manager.get(name=selected_journey)

        return redirect("journey_details", pk=patient_journey_entry.pk)


class JourneyDetailView(generic.DetailView):
    """View for displaying the details of a patient journey."""

    model = PatientJourney
    template_name = "journey_details.html"

    def get_context_data(self, **kwargs):
        """Add patient journey to context."""
        context = super().get_context_data(**kwargs)
        patient_journey = self.get_object()
        context["patient_journey"] = patient_journey
        self.request.session["patient_journey_id"] = patient_journey.id

        return context

    def post(self, request, *args, **kwargs):
        """Redirect to the FilterView afterward."""
        patient_journey_id = self.request.session.get("patient_journey_id")
        patient_journey = PatientJourney.manager.get(pk=patient_journey_id)
        configuration = ExtractionConfiguration(
            patient_journey=patient_journey.patient_journey
        )
        orchestrator = Orchestrator(configuration)
        orchestrator.set_db_objects_id("patient_journey", patient_journey_id)

        return redirect("journey_filter")


class JourneyFilterView(generic.FormView):
    """View for selecting extraction results filter"""

    form_class = FilterForm
    template_name = "filter_journey.html"
    success_url = reverse_lazy("result")

    def get_context_data(self, **kwargs):
        """Add session variable to context."""
        context = super().get_context_data(**kwargs)
        context["is_comparing"] = self.request.session.get("is_comparing")

        return context

    def form_valid(self, form):
        """Run extraction pipeline and save the filter settings in the cache."""
        orchestrator = Orchestrator.get_instance()
        orchestrator.get_configuration().update(
            event_types=form.cleaned_data["event_types"],
            locations=form.cleaned_data["locations"],
        )
        orchestrator.run(view=self)
        single_trace_df = orchestrator.get_data()
        single_trace_df = utils.Conversion.prepare_df_for_xes_conversion(
            single_trace_df, orchestrator.get_configuration().activity_key
        )
        utils.Conversion.create_xes(
            utils.CSV_OUTPUT,
            name="single_trace",
            key=orchestrator.get_configuration().activity_key,
        )
        self.request.session["is_extracted"] = True
        self.request.session.save()

        if self.request.session.get("is_comparing") is True:
            orchestrator.save_results_to_db()
            return redirect(reverse_lazy("testing_comparison"))

        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        """Return a JSON response with the current progress of the pipeline."""
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            progress_information = {
                "progress": self.request.session.get("progress"),
                "status": self.request.session.get("status"),
            }
            return JsonResponse(progress_information)

        self.request.session["is_extracted"] = False
        self.request.session["progress"] = 0
        self.request.session["status"] = None
        self.request.session.save()

        return super().get(request, *args, **kwargs)


class ResultView(generic.FormView):
    """View for displaying the result."""

    form_class = ResultForm
    template_name = "result.html"
    success_url = reverse_lazy("result")

    def get_context_data(self, **kwargs):
        """Prepare the data for the result page."""
        context = super().get_context_data(**kwargs)
        orchestrator = Orchestrator.get_instance()
        event_types = orchestrator.get_configuration().event_types
        filter_dict = {
            "concept:name": event_types,
            "attribute_location": orchestrator.get_configuration().locations,
        }

        output_path_xes = f"{str(utils.output_path / 'single_trace')}_event_type.xes"
        single_trace_df = pm4py.read_xes(output_path_xes)
        single_trace_df.rename(
            columns={"time:timestamp": "start_timestamp"}, inplace=True
        )

        # 2. Sort and filter the single journey dataframe
        single_trace_df = single_trace_df.sort_values(
            by="start_timestamp", inplace=False
        )
        single_trace_df_filtered = utils.DataFrameUtilities.filter_dataframe(
            single_trace_df, filter_dict
        )
        # 3. Append the single journey dataframe to the all traces dataframe

        # TODO: remove comment once cohort is implemented
        # condition = Cohort.manager.get(pk=orchestrator.get_db_objects_id("cohort")).condition
        # query = Q(cohort__condition=condition)
        all_traces_df = utils.DataFrameUtilities.get_events_df()
        if not all_traces_df.empty:
            all_traces_df = utils.Conversion.prepare_df_for_xes_conversion(
                all_traces_df, orchestrator.get_configuration().activity_key
            )
            utils.Conversion.align_df_datatypes(single_trace_df_filtered, all_traces_df)
            all_traces_df = pd.concat(
                [all_traces_df, single_trace_df_filtered],
                ignore_index=True,
                axis="rows",
            )
            all_traces_df = all_traces_df.groupby(
                "case:concept:name", group_keys=False, sort=False
            ).apply(lambda x: x.sort_values(by="start_timestamp", inplace=False))

            all_traces_df_filtered = utils.DataFrameUtilities.filter_dataframe(
                all_traces_df, filter_dict
            )
        else:
            all_traces_df_filtered = single_trace_df_filtered

        # 4. Save all information in context to display on website
        context.update(
            {
                "form": ResultForm(
                    initial={
                        "event_types": orchestrator.get_configuration().event_types,
                        "locations": orchestrator.get_configuration().locations,
                    }
                ),
                "journey": orchestrator.get_configuration().patient_journey,
                "dfg_img": utils.Conversion.create_dfg_from_df(
                    single_trace_df_filtered
                ),
                "xes_html": utils.Conversion.create_html_from_xes(
                    single_trace_df_filtered
                ).getvalue(),
                "all_dfg_img": utils.Conversion.create_dfg_from_df(
                    all_traces_df_filtered
                ),
                "all_xes_html": utils.Conversion.create_html_from_xes(
                    all_traces_df_filtered
                ).getvalue(),
            }
        )

        # Generate XES files
        single_trace_xes = utils.Conversion.dataframe_to_xes(
            single_trace_df_filtered, "single_trace.xes"
        )
        all_traces_xes = utils.Conversion.dataframe_to_xes(
            all_traces_df_filtered, "all_traces.xes"
        )

        # Store XES in session for retrieval in DownloadXesView
        self.request.session["single_trace_xes"] = str(single_trace_xes)
        self.request.session["all_traces_xes"] = str(all_traces_xes)

        return context

    def form_valid(self, form):
        """Save the filter settings in the cache."""
        orchestrator = Orchestrator.get_instance()
        orchestrator.get_configuration().update(
            # This should not be necessary, unspecified values should be unchanged
            patient_journey=orchestrator.get_configuration().patient_journey,
            event_types=form.cleaned_data["event_types"],
            locations=form.cleaned_data["locations"],
        )

        return super().form_valid(form)


class SaveSuccessView(generic.TemplateView):
    """View for displaying the save success page."""

    template_name = "save_success.html"

    def get_context_data(self, **kwargs):
        """Prepare the data for the save success page."""
        context = super().get_context_data(**kwargs)
        orchestrator = Orchestrator.get_instance()
        orchestrator.save_results_to_db()

        return context


class DownloadXesView(View):
    """Download one or more XES files based on the types specified in POST request,
    bundled into a ZIP file if multiple."""

    def post(self, request, *args, **kwargs):
        """Processes a POST request to download specified trace types as XES files.
        Validates trace types and prepares the appropriate file response."""
        trace_types = self.get_trace_types(request)
        if not trace_types:
            return HttpResponse("No file type specified.", status=400)

        files_to_download = self.collect_files(request, trace_types)
        if (
            files_to_download is None
        ):  # Check for None explicitly to handle error scenario
            return HttpResponse("One or more files could not be found.", status=404)

        return self.prepare_response(files_to_download)

    def get_trace_types(self, request):
        """Retrieves a list of trace types from the POST data."""

        return request.POST.getlist("trace_type[]")

    def collect_files(self, request, trace_types):
        """Collects file for the specified trace types to download, checking for their existence."""
        files_to_download = []
        for trace_type in trace_types:
            file_path = self.process_trace_type(request, trace_type)
            if file_path:
                if os.path.exists(file_path):
                    files_to_download.append(file_path)
                else:
                    return None  # Return None if any file path is invalid

        return files_to_download

    def process_trace_type(self, request, trace_type):
        """Process and provide the XES files to be downloaded based on the trace type."""
        if trace_type == "all_traces":
            return request.session.get("all_traces_xes")
        if trace_type == "single_trace":
            return request.session.get("single_trace_xes")

        return None  # Return None for unrecognized trace type

    def prepare_response(self, files_to_download):
        """Prepares the appropriate response based on the number of files to be downloaded."""
        if len(files_to_download) == 1:
            return self.single_file_response(files_to_download[0])

        return self.zip_files_response(files_to_download)

    # pylint: disable=consider-using-with
    def single_file_response(self, file_path):
        """Prepares a file if there is only a single XES file."""
        file = open(file_path, "rb")
        response = FileResponse(file, as_attachment=True)
        response[
            "Content-Disposition"
        ] = f'attachment; filename="{os.path.basename(file_path)}"'

        return response

    def zip_files_response(self, files_to_download):
        """Prepares a zip file if there are multiple XES files using a temporary file."""
        temp_zip = NamedTemporaryFile(mode="w+b", suffix=".zip", delete=False)
        zipf = zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED)
        for file_path in files_to_download:
            zipf.write(file_path, arcname=os.path.basename(file_path))
        zipf.close()
        temp_zip_path = temp_zip.name
        temp_zip.close()

        file = open(temp_zip_path, "rb")
        response = FileResponse(file, as_attachment=True)
        response[
            "Content-Disposition"
        ] = 'attachment; filename="downloaded_xes_files.zip"'

        return response
