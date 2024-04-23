from django.views.generic import TemplateView
from django.shortcuts import render, redirect
from .forms import ApiKeyForm
import os


class TracexLandingPage(TemplateView):
    template_name = "landing_page.html"

    def get(self, request, *args, **kwargs):
        form = ApiKeyForm()
        context = self.get_context_data(**kwargs)
        context['form'] = form

        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        form = ApiKeyForm(request.POST)
        if form.is_valid():
            api_key = form.cleaned_data['api_key']
            os.environ['OPENAI_API_KEY'] = api_key  # This sets it for the current process only

            return redirect('landing_page')
        else:

            return render(request, self.template_name, {'form': form})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        api_key = os.getenv('OPENAI_API_KEY')
        print(api_key)
        context['prompt_for_key'] = not bool(api_key)
        print(context['prompt_for_key'])

        return context
