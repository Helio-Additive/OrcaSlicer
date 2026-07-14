#ifndef slic3r_HelioRetryPolicy_hpp_
#define slic3r_HelioRetryPolicy_hpp_

#include <string>

#include "nlohmann/json_fwd.hpp"

namespace Slic3r {

enum class HelioRetryKind
{
    None,
    Transient,
    BackendAuth
};

inline constexpr const char HELIO_BACKEND_AUTH_401_MESSAGE[] =
    "Authentication failed: Auth service returned status 401";

bool helio_is_terminal_http_status(unsigned status) noexcept;
bool helio_is_transient_http_status(unsigned status) noexcept;
bool helio_is_transient_error_message(const std::string& message);

bool helio_has_graphql_errors(const nlohmann::json& response);
bool helio_has_exact_backend_auth_error(const nlohmann::json& response);

HelioRetryKind helio_classify_graphql_response(unsigned status, const nlohmann::json& response);
HelioRetryKind helio_classify_graphql_response(unsigned status, const std::string& body);

HelioRetryKind helio_classify_retry(unsigned status,
                                    const std::string& body = std::string(),
                                    const std::string& transport_error = std::string());

const char* helio_retry_kind_name(HelioRetryKind kind) noexcept;

class HelioRetryController
{
public:
    explicit HelioRetryController(unsigned max_consecutive_backend_auth_retries = 1) noexcept;

    bool should_retry(HelioRetryKind kind) noexcept;
    void reset() noexcept;

    unsigned consecutive_backend_auth_failures() const noexcept;
    unsigned max_consecutive_backend_auth_retries() const noexcept;

private:
    unsigned m_consecutive_backend_auth_failures{0};
    unsigned m_max_consecutive_backend_auth_retries{1};
};

} // namespace Slic3r

#endif // slic3r_HelioRetryPolicy_hpp_
