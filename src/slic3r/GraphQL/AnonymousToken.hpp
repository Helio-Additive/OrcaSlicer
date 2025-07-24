#ifndef helio_AnonymousToken_hpp_
#define helio_AnonymousToken_hpp_

#include "QueryResultBase.hpp"

namespace Helio {
	class QueryResultBase;
	class ResultFromUnsuccessfulQuery;

	class AnonymousToken
	{
    public:

		class Result: public QueryResultBase
		{
		private:
			std::string token;

		public:
			Result(unsigned status, bool success, std::string error, std::string token) : token(token), QueryResultBase(status, success, error){}
            Result() { QueryResultBase(); }
			void init(unsigned status, bool success, std::string error, std::string token) {
                this->token = "Bearer " + token;
                QueryResultBase::init(status, success, error);
			}
            std::string getToken() { 
				if (isSuccess())
                    return token;
                else
                    throw ResultFromUnsuccessfulQuery(getError());
			};
		};

        static Result get_anonymous_token(const std::string helio_api_url);
	};
}

#endif
