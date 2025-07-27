#ifndef helio_Materials_hpp_
#define helio_Materials_hpp_

#include <boost/algorithm/string.hpp>
#include "QueryResultBase.hpp"
#include "QueryBase.hpp"
#include <optional>

namespace Helio {

	class Material
	{
    private:
        std::string id;
        std::string name;
        std::string orca_name;

	public:
        Material(std::string id, std::string name, std::string orca_name) : name(name), id(id), orca_name(orca_name) {}
        std::string getId() { return id; }
        std::optional<std::string> checkNameMatch(std::string filament_name);
	};

	class Materials: QueryBase
	{
    public:
        class Result : public QueryResultBase
        {
        private:
            std::vector<Material> materials;

		public:
			Result(unsigned status, bool success, std::string error, std::vector<Material> materials) : materials(materials), QueryResultBase(status, success, error){}
            Result() { QueryResultBase(); }
            std::vector<Material> getMaterials();
            std::optional<std::string> getMaterildIdByName(std::string name);
            Result mergeResults(Result resB);
        };

        std::optional<int> page;
        std::optional<int> page_size;

        Materials(std::optional<int> page, std::optional<int> page_size, std::string helio_api_url, std::string helio_api_auth_token) : page(page), page_size(page_size), QueryBase(helio_api_url, helio_api_auth_token) {}
        Materials(std::string helio_api_url, std::string helio_api_auth_token): QueryBase(helio_api_url, helio_api_auth_token) {}
        Result getAllMaterials();
    };
}
#endif
