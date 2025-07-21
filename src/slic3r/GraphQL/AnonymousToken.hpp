#ifndef helio_AnonymousToken_hpp_
#define helio_AnonymousToken_hpp_

namespace Helio {
	class QueryResultBase;
	class ResultFromUnsuccessfulQuery;

	class AnonymousToken
	{
    public:

		class Result:QueryResultBase
		{
		private:
			std : string token;

		public:
			AnonymousTokenResult(unsigned status, bool success, std::string error, std::string token) : token(token), QueryResultBase(status, success, error){}
            AnonymousTokenResult() {}
			init(unsigned status, bool success, std::string error, std::string token) : token(token), QueryResultBase::init(status, success, error){}
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
