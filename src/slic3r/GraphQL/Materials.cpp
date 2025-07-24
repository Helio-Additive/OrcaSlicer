#include "Materials.hpp"
#include "nlohmann/json.hpp"
#include "slic3r/Utils/Http.hpp"

std::vector<Helio::Material> Helio::Materials::Result::getMaterials() {
	if (isSuccess())
		return this->materials;
	else
		throw ResultFromUnsuccessfulQuery(getError());
}

std::optional<std::string> Helio::Materials::Result::getMaterildIdByName(std::string name) {
    std::vector<Material> materials = this->getMaterials();
    std::optional<std::string> id;
	for (Material& material: materials) {
        id = material.checkNameMatch(name);

		if (id.has_value())
            break;
	}

	return id;
}

Helio::Materials::Result Helio::Materials::Result::mergeResults(Helio::Materials::Result resB) { 
    std::vector<Material> current_materials = this->isSuccess() ? this->getMaterials() : std::vector<Material>{}; 
    std::vector<Material> new_materials = resB.isSuccess() ? resB.getMaterials() : std::vector<Material>{}; 

    std::vector<Material> merged;
    merged.reserve(current_materials.size() + new_materials.size()); // Optional: improves performance
    merged.insert(merged.end(), current_materials.begin(), current_materials.end());
    merged.insert(merged.end(), new_materials.begin(), new_materials.end());

    bool success = this->isSuccess()  && resB.isSuccess();
    std::string error   = this->getError();
    unsigned status = this->getStatus();

    if (!resB.isSuccess()) {
        error = resB.getError();
        status = resB.getStatus();
    }

    return Helio::Materials::Result(status, success, error, merged);
}

Helio::Materials::Result Helio::Materials::getAllMaterials()
{
    std::string request_template = R"( { 
										"query": "%1%", 
										"variables": %2% 
									} )";

    std::string query = "query Materials($pageSize: Int, $page: Int) { materials(pageSize: $pageSize page: $page) { pages objects { ... on Material { id name alternativeNames { bambustudio } } } } }";

    int                      num_pages = 0;
    Helio::Materials::Result res;

    std::string variables = R"({})";

    std::string request = (boost::format(request_template) % query % variables).str();

    std::string end_point = this->getEndPointUrl();
    std::string auth_token = this->getAuthToken();


	auto http_call = [&num_pages, &end_point, &auth_token](Helio::Materials::Result &res_object, std::string request) {
		auto http = Slic3r::Http::post(end_point);
		http.header("Content-Type", "application/json").header("Authorization", auth_token).set_post_body(request);

		http.timeout_connect(20)
			.timeout_max(100)
			.on_complete([&res_object, &num_pages](std::string body, unsigned status) {
				if (status == 200) {
					nlohmann::json parsed_obj = nlohmann::json::parse(body);
                    num_pages      = parsed_obj["data"]["materials"]["pages"];
					std::vector<Material> materials;
					for (const auto& material : parsed_obj["data"]["materials"]["objects"]) {
						std::string                id   = material["id"];
						std::string                name = material["name"];
                        std::string                altName;
                        if (material.contains("alternativeNames") && material["alternativeNames"].contains("bambustudio") &&
                            !material["alternativeNames"]["bambustudio"].is_null()) {
                            altName = material["alternativeNames"]["bambustudio"].get<std::string>();
                        } else {
                            altName = ""; 
                        }
						materials.emplace_back(id, name, altName);
					}
					res_object = Helio::Materials::Result(status, true, "", materials);
				} else {
					res_object = Helio::Materials::Result(status, false, "Server Error: " + body, {});
				}
			})
			.on_error([&res_object](std::string body, std::string error, unsigned status) {
				error  = (boost::format("error: %1%, message: %2%") % error % body).str();
				res_object = Helio::Materials::Result(status, false, error, {});
			})
			.perform_sync();
    };

	http_call(res, request);

	for (int i = 2; i <= num_pages; i++) {
        if (!res.isSuccess())
            break;

		Helio::Materials::Result newRes;
		variables = (boost::format(R"({"page":%1%})") % i).str();
		request = (boost::format(request_template) % query % variables).str();

		http_call(newRes, request);

		res = res.mergeResults(newRes);
	}

	return res;
}