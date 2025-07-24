#ifndef helio_QueryBase_hpp_
#define helio_QueryBase_hpp_

#include <boost/algorithm/string.hpp>
#include "QueryResultBase.hpp"
#include <optional>

namespace Helio {
	class QueryBase
	{
    private: 
		std::string helio_api_endpoint;
		std::string helio_api_auth_token;

	public:
        QueryBase(std::string helio_api_url, std::string helio_api_auth_token) : helio_api_endpoint(helio_api_url + "/graphql"), helio_api_auth_token(helio_api_auth_token)  {}
        std::string getEndPointUrl() { return helio_api_endpoint; }
        std::string getAuthToken() { return helio_api_auth_token; }
    };
}

#endif
