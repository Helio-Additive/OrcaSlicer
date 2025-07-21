#include "AnonymousToken.hpp"
#include "QueryResultBase.hpp"

namespace Helio {
	AnonymousToken::Result AnonymousToken::get_anonymous_token(const std::string helio_api_url) {
    AnonymousToken::Result res = AnonymousToken::Result();
	std::string token_endpoint = helio_api_url + "/rest/auth/anonymous_token/orcaslicer";
    auto http = Http::get(token_endpoint);

    http.timeout_connect(20)
        .timeout_max(100)
        .on_complete([&res](std::string body, unsigned status) {
            nlohmann::json parsed_obj = nlohmann::json::parse(body);
            if (status == 200) {
                res.init(status, true, "", parsed_obj["pat"]);
            } else {
                res.init(status, false, "Server Error: " + body, "");
            }
        })
        .on_error([&res](std::string body, std::string error, unsigned status) {
            std::string error  = (boost::format("error: %1%, message: %2%") % error % body).str();
            res.init(status, false, error, "");
        })
        .perform_sync();

    return res;

}
}