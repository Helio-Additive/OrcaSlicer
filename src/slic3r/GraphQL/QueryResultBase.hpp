#ifndef helio_QueryResultBase_hpp_
#define helio_QueryResultBase_hpp_

namespace Helio {
	class QueryResultBase
	{
    private:
        unsigned status;
        bool     success;
        std::string error;

	public:
        QueryResultBase(unsigned status, bool success, std::string error) : status(status), success(success), error(std::move(error)) {}
        QueryResultBase():status(0), success(false){}
        void init(unsigned status, bool success, std::string error) { 
            this->status = status;
            this->success = success;
            this->error = error;
        }

        unsigned getStatus() { return status; }
        bool     isSuccess() { return success; }
        std::string     getError() { return error; }
	};

    class ResultFromUnsuccessfulQuery: public std::exception
    {
        std::string message;
    public:
        ResultFromUnsuccessfulQuery(std::string msg) : message(std::move(msg)) {}
        const char* what() const noexcept override { return message.c_str(); }
    };
    }

#endif
