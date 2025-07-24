#include "Printers.hpp"
#include "nlohmann/json.hpp"
#include "slic3r/Utils/Http.hpp"

std::vector<Helio::Printer> Helio::Printers::Result::getPrinters() {
	if (isSuccess())
		return this->printers;
	else
		throw ResultFromUnsuccessfulQuery(getError());
}

std::optional<std::string> Helio::Printers::Result::getPrinterIdByName(std::string name) {
    std::vector<Printer> printers = this->getPrinters();
    std::optional<std::string> id;
	for (Printer& printer: printers) {
        id = printer.checkNameMatch(name);

		if (id.has_value())
            break;
	}

	return id;
}

Helio::Printers::Result Helio::Printers::Result::mergeResults(Helio::Printers::Result resB) { 
    std::vector<Printer> current_printers = this->isSuccess() ? this->getPrinters() : std::vector<Printer>{}; 
    std::vector<Printer> new_printers = resB.isSuccess() ? resB.getPrinters() : std::vector<Printer>{}; 

    std::vector<Printer> merged;
    merged.reserve(current_printers.size() + new_printers.size()); // Optional: improves performance
    merged.insert(merged.end(), current_printers.begin(), current_printers.end());
    merged.insert(merged.end(), new_printers.begin(), new_printers.end());

    bool success = this->isSuccess()  && resB.isSuccess();
    std::string error   = this->getError();
    unsigned status = this->getStatus();

    if (!resB.isSuccess()) {
        error = resB.getError();
        status = resB.getStatus();
    }

    return Helio::Printers::Result(status, success, error, merged);
}

Helio::Printers::Result Helio::Printers::getAllPrinters()
{
    std::string request_template = R"( { 
										"query": "%1%", 
										"variables": %2% 
									} )";

    std::string query = "query Printers($pageSize: Int, $page: Int) { printers(pageSize: $pageSize page: $page) { pages objects { ... on Printer { id name alternativeNames { bambustudio } } } } }";

    int                      num_pages = 0;
    Helio::Printers::Result res;

    std::string variables = R"({})";

    std::string request = (boost::format(request_template) % query % variables).str();

    std::string end_point = this->getEndPointUrl();
    std::string auth_token = this->getAuthToken();


	auto http_call = [&num_pages, &end_point, &auth_token](Helio::Printers::Result &res_object, std::string request) {
		auto http = Slic3r::Http::post(end_point);
		http.header("Content-Type", "application/json").header("Authorization", auth_token).set_post_body(request);

		http.timeout_connect(20)
			.timeout_max(100)
			.on_complete([&res_object, &num_pages](std::string body, unsigned status) {
				if (status == 200) {
					nlohmann::json parsed_obj = nlohmann::json::parse(body);
                    num_pages      = parsed_obj["data"]["printers"]["pages"];
					std::vector<Printer> printers;
					for (const auto& printer : parsed_obj["data"]["printers"]["objects"]) {
						std::string                id   = printer["id"];
						std::string                name = printer["name"];
                        std::string                altName;
                        if (printer.contains("alternativeNames") && printer["alternativeNames"].contains("bambustudio") &&
                            !printer["alternativeNames"]["bambustudio"].is_null()) {
                            altName = printer["alternativeNames"]["bambustudio"].get<std::string>();
                        } else {
                            altName = ""; 
                        }
						printers.emplace_back(id, name, altName);
					}
					res_object = Helio::Printers::Result(status, true, "", printers);
				} else {
					res_object = Helio::Printers::Result(status, false, "Server Error: " + body, {});
				}
			})
			.on_error([&res_object](std::string body, std::string error, unsigned status) {
				error  = (boost::format("error: %1%, message: %2%") % error % body).str();
				res_object = Helio::Printers::Result(status, false, error, {});
			})
			.perform_sync();
    };

	http_call(res, request);

	for (int i = 2; i <= num_pages; i++) {
        if (!res.isSuccess())
            break;

		Helio::Printers::Result newRes;
		variables = (boost::format(R"({"page":%1%})") % i).str();
		request = (boost::format(request_template) % query % variables).str();

		http_call(newRes, request);

		res = res.mergeResults(newRes);
	}

	return res;
}