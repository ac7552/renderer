module Api
  module V1
    # JSON for the web page and the mobile app. Who's asking comes from the page's session cookie
    # (Authentication): where the site needs a sign-in (Gate), so does the API.
    class BaseController < ActionController::API
      include ActionController::Cookies
      include Authentication
      wrap_parameters false
      before_action :require_admission

      rescue_from SizeChart::NotFound do |error|
        render json: { error: "not_found", message: error.message }, status: :not_found
      end
    end
  end
end
