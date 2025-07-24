#ifndef helio_Printers_hpp_
#define helio_Printers_hpp_

#include <boost/algorithm/string.hpp>
#include "QueryResultBase.hpp"
#include "QueryBase.hpp"
#include <optional>

namespace Helio {

	class Printer
	{
    private:
        std::string id;
        std::string name;
        std::string orca_name;

	public:
        Printer(std::string id, std::string name, std::string orca_name) : name(name), id(id), orca_name(orca_name) {}
        std::string getId() { return id; }
        std::optional<std::string> checkNameMatch(std::string printer_name) { 
            if (boost::algorithm::icontains(printer_name, name) || boost::algorithm::icontains(printer_name, orca_name))
                return id;
            else
                return std::nullopt;
        }
	};

	class Printers: QueryBase
	{
    public:
        class Result : public QueryResultBase
        {
        private:
            std::vector<Printer> printers;

		public:
			Result(unsigned status, bool success, std::string error, std::vector<Printer> printers) : printers(printers), QueryResultBase(status, success, error){}
            Result() { QueryResultBase(); }
            std::vector<Printer> getPrinters();
            std::optional<std::string> getPrinterIdByName(std::string name);
            Result mergeResults(Result resB);
        };

        std::optional<int> page;
        std::optional<int> page_size;

        Printers(std::optional<int> page, std::optional<int> page_size, std::string helio_api_url, std::string helio_api_auth_token) : page(page), page_size(page_size), QueryBase(helio_api_url, helio_api_auth_token) {}
        Printers(std::string helio_api_url, std::string helio_api_auth_token): QueryBase(helio_api_url, helio_api_auth_token) {}
        Result getAllPrinters();
    };
}
#endif
