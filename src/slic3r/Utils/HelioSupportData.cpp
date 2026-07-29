#include "HelioSupportData.hpp"

#include "nlohmann/json.hpp"

#include <exception>
#include <iterator>
#include <sstream>
#include <utility>

namespace Slic3r {

namespace {

using json = nlohmann::json;

std::string catalog_name(SupportDataCatalogKind kind)
{
    return kind == SupportDataCatalogKind::Printers ? "printers" : "materials";
}

std::string http_error(const SupportDataHttpResponse& response)
{
    if (!response.error.empty()) {
        return response.error;
    }

    std::ostringstream message;
    message << "HTTP status: " << response.status;
    if (!response.body.empty()) {
        message << ", body: " << response.body;
    }
    return message.str();
}

std::string graphql_error(const json& response)
{
    if (!response.contains("errors")) {
        return {};
    }

    const json& errors = response["errors"];
    std::ostringstream message;

    if (errors.is_array()) {
        bool first = true;
        for (const json& error : errors) {
            if (!error.is_object() || !error.contains("message") || !error["message"].is_string()) {
                continue;
            }
            if (!first) {
                message << '\n';
            }
            message << error["message"].get<std::string>();
            first = false;
        }
    } else if (errors.is_object() && errors.contains("message") && errors["message"].is_string()) {
        message << errors["message"].get<std::string>();
    }

    const std::string result = message.str();
    return result.empty() ? errors.dump() : result;
}

SupportDataPageResult failed_page(const SupportDataHttpResponse& response,
                                  HelioRetryKind                 retry_kind,
                                  std::string                    error)
{
    SupportDataPageResult result;
    result.status     = response.status;
    result.retry_kind = retry_kind;
    result.error      = std::move(error);
    result.trace_id   = response.trace_id;
    return result;
}

SupportDataPageResult incomplete_page(const SupportDataHttpResponse& response, std::string error)
{
    return failed_page(response, HelioRetryKind::Transient, std::move(error));
}

bool required_string(const json& object, const char* key, std::string& value)
{
    if (!object.contains(key) || !object[key].is_string()) {
        return false;
    }
    value = object[key].get<std::string>();
    return !value.empty();
}

void log_attempt(const SupportDataCatalogStore::Logger& logger, const SupportDataLoadAttempt& attempt) noexcept
{
    if (!logger) {
        return;
    }
    try {
        logger(attempt);
    } catch (...) {
    }
}

} // namespace

SupportDataPageResult parse_support_data_page(SupportDataCatalogKind        kind,
                                              int                           page,
                                              const SupportDataHttpResponse& response)
{
    const HelioRetryKind response_retry_kind = helio_classify_retry(response.status, response.body, response.error);

    if (response.status != 200) {
        return failed_page(response, response_retry_kind, http_error(response));
    }

    json parsed;
    try {
        parsed = json::parse(response.body);
    } catch (const std::exception& e) {
        return incomplete_page(response, std::string("Malformed Helio support-data response: ") + e.what());
    } catch (...) {
        return incomplete_page(response, "Malformed Helio support-data response");
    }

    if (helio_has_graphql_errors(parsed)) {
        return failed_page(response, response_retry_kind, graphql_error(parsed));
    }

    const std::string payload_name = catalog_name(kind);
    if (!parsed.contains("data") || !parsed["data"].is_object() ||
        !parsed["data"].contains(payload_name) || !parsed["data"][payload_name].is_object()) {
        return incomplete_page(response, "Helio support-data response is missing data." + payload_name);
    }

    const json& payload = parsed["data"][payload_name];
    if (!payload.contains("pages") || !payload["pages"].is_number_integer() ||
        !payload.contains("pageInfo") || !payload["pageInfo"].is_object() ||
        !payload["pageInfo"].contains("hasNextPage") || !payload["pageInfo"]["hasNextPage"].is_boolean() ||
        !payload.contains("objects") || !payload["objects"].is_array()) {
        return incomplete_page(response, "Helio " + payload_name + " page metadata is incomplete");
    }

    int  total_pages = 0;
    bool has_next_page = false;
    try {
        total_pages   = payload["pages"].get<int>();
        has_next_page = payload["pageInfo"]["hasNextPage"].get<bool>();
    } catch (const std::exception& e) {
        return incomplete_page(response, std::string("Helio ") + payload_name + " pagination metadata is invalid: " + e.what());
    } catch (...) {
        return incomplete_page(response, "Helio " + payload_name + " pagination metadata is invalid");
    }
    const json& objects = payload["objects"];

    if (page < 1 || total_pages < 1 || page > total_pages || objects.empty()) {
        return incomplete_page(response, "Helio " + payload_name + " page is empty or out of range");
    }
    if ((has_next_page && page >= total_pages) || (!has_next_page && page < total_pages)) {
        return incomplete_page(response, "Helio " + payload_name + " pagination metadata is inconsistent");
    }

    SupportDataPageResult result;
    result.status        = response.status;
    result.trace_id      = response.trace_id;
    result.total_pages   = total_pages;
    result.has_next_page = has_next_page;

    try {
        for (const json& object : objects) {
            if (!object.is_object()) {
                return incomplete_page(response, "Helio " + payload_name + " page contains an invalid object");
            }

            HelioSupportedData item;
            if (!required_string(object, "id", item.id) || !required_string(object, "name", item.name)) {
                return incomplete_page(response, "Helio " + payload_name + " page contains an incomplete object");
            }

            if (kind == SupportDataCatalogKind::Printers) {
                // An explicit null means "capability unspecified", not "malformed": treat
                // it as unknown and keep the default (false), matching how the previous
                // loader and the alternativeNames handling below deal with nulls. Failing
                // the page here would reject it identically on every retry and could leave
                // the whole printer catalog Failed over one unspecified printer.
                if (object.contains("heatedChamber") && !object["heatedChamber"].is_null()) {
                    if (!object["heatedChamber"].is_boolean()) {
                        return incomplete_page(response, "Helio printers page contains an invalid heatedChamber value");
                    }
                    item.heated_chamber = object["heatedChamber"].get<bool>();
                }
            } else {
                if (!required_string(object, "feedstock", item.feedstock)) {
                    continue;
                }
            }

            if (object.contains("alternativeNames") && !object["alternativeNames"].is_null()) {
                if (!object["alternativeNames"].is_object()) {
                    return incomplete_page(response, "Helio " + payload_name + " page contains invalid alternativeNames");
                }
                const json& alternative_names = object["alternativeNames"];
                if (alternative_names.contains("bambustudio") && !alternative_names["bambustudio"].is_null()) {
                    if (!alternative_names["bambustudio"].is_string()) {
                        return incomplete_page(response, "Helio " + payload_name + " page contains an invalid Bambu Studio name");
                    }
                    item.native_name = alternative_names["bambustudio"].get<std::string>();
                }
            }

            if (kind == SupportDataCatalogKind::Materials && item.native_name.empty()) {
                item.native_name = item.name;
            }

            if (kind == SupportDataCatalogKind::Printers || item.feedstock == "FILAMENT") {
                result.items.push_back(std::move(item));
            }
        }
    } catch (const std::exception& e) {
        return incomplete_page(response, std::string("Failed to parse Helio ") + payload_name + " page: " + e.what());
    } catch (...) {
        return incomplete_page(response, "Failed to parse Helio " + payload_name + " page");
    }

    result.success    = true;
    result.retry_kind = HelioRetryKind::None;
    return result;
}

SupportDataAvailability support_data_availability(const SupportDataCatalogView& printers,
                                                  const SupportDataCatalogView& materials) noexcept
{
    if (printers.has_usable_snapshot() && materials.has_usable_snapshot()) {
        return SupportDataAvailability::Usable;
    }

    if ((!printers.has_usable_snapshot() && printers.state == SupportDataLoadState::Failed) ||
        (!materials.has_usable_snapshot() && materials.state == SupportDataLoadState::Failed)) {
        return SupportDataAvailability::LoadFailed;
    }

    if ((!printers.has_usable_snapshot() &&
         (printers.state == SupportDataLoadState::NotLoaded || printers.state == SupportDataLoadState::Loading)) ||
        (!materials.has_usable_snapshot() &&
         (materials.state == SupportDataLoadState::NotLoaded || materials.state == SupportDataLoadState::Loading))) {
        return SupportDataAvailability::Synchronizing;
    }

    return SupportDataAvailability::LoadFailed;
}

SupportDataCatalogStore::SupportDataCatalogStore(SupportDataCatalogKind kind)
    : m_kind(kind)
{}

bool SupportDataCatalogStore::try_begin(bool force_refresh)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_state == SupportDataLoadState::Loading) {
        if (force_refresh) {
            // A load is already in flight (e.g. from Helio startup) and it may be using
            // stale credentials (e.g. the user just linked/replaced a PAT). Queue a
            // follow-up refresh instead of discarding this request outright: once the
            // in-flight run finishes, the caller re-checks consume_pending_refresh() and
            // re-triggers a fresh load with current credentials.
            m_pending_refresh = true;
        }
        return false;
    }
    if (m_snapshot && !force_refresh) {
        return false;
    }
    if (m_state == SupportDataLoadState::Ready && !force_refresh) {
        return false;
    }

    m_state            = SupportDataLoadState::Loading;
    m_last_error.clear();
    m_run_claimed      = false;
    m_pending_refresh  = false;
    return true;
}

bool SupportDataCatalogStore::consume_pending_refresh()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_pending_refresh) {
        return false;
    }
    m_pending_refresh = false;
    return true;
}

bool SupportDataCatalogStore::has_pending_refresh() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_pending_refresh;
}

bool SupportDataCatalogStore::begin_pending_refresh()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_pending_refresh) {
        return false;
    }
    if (m_state == SupportDataLoadState::Loading) {
        // Another run currently owns the store — e.g. invalidate() revoked this caller
        // and a replacement load was started under the new generation. Only the run that
        // actually completed (leaving the store Ready/Failed) may start the queued
        // refresh; clearing m_run_claimed here would let a second worker claim the store
        // concurrently and race to publish.
        return false;
    }
    m_pending_refresh = false;
    m_state           = SupportDataLoadState::Loading;
    m_last_error.clear();
    m_run_claimed     = false;
    return true;
}

void SupportDataCatalogStore::invalidate()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    // Bumping the generation revokes any in-flight run: it stops fetching at the next
    // page boundary, and neither publish() nor fail() will touch the store afterwards.
    // Without this, a load started with the previous PAT could still publish that
    // account's catalog, and the next non-forced request would accept it as current.
    ++m_generation;
    m_snapshot.reset();
    m_state           = SupportDataLoadState::NotLoaded;
    m_last_error.clear();
    m_run_claimed     = false;
    m_pending_refresh = false;
}

bool SupportDataCatalogStore::claim_run(std::uint64_t& run_generation)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_state != SupportDataLoadState::Loading || m_run_claimed) {
        return false;
    }
    m_run_claimed  = true;
    run_generation = m_generation;
    return true;
}

bool SupportDataCatalogStore::is_run_current(std::uint64_t run_generation) const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return run_generation == m_generation;
}

bool SupportDataCatalogStore::run(const PageFetcher&   fetcher,
                                  const RetrySleeper& sleeper,
                                  const Logger&       logger)
{
    std::uint64_t run_generation = 0;
    if (!claim_run(run_generation)) {
        return false;
    }

    try {
        return run_impl(fetcher, sleeper, logger, run_generation);
    } catch (const std::exception& e) {
        fail(std::string("Helio support-data load failed: ") + e.what(), run_generation);
    } catch (...) {
        fail("Helio support-data load failed", run_generation);
    }
    return false;
}

bool SupportDataCatalogStore::run_impl(const PageFetcher&   fetcher,
                                       const RetrySleeper& sleeper,
                                       const Logger&       logger,
                                       std::uint64_t       run_generation)
{
    if (!fetcher) {
        fail("No Helio support-data page fetcher was provided", run_generation);
        return false;
    }

    std::vector<HelioSupportedData> staging;
    int                             page = 1;
    int                             expected_total_pages = 0;
    int                             restarts_remaining = MAX_PAGINATION_RESTARTS;

    while (true) {
        // The credentials this run started with may have been revoked (PAT change,
        // logout, Helio disabled). Stop before spending another page request.
        if (!is_run_current(run_generation)) {
            return false;
        }

        SupportDataPageResult page_result;
        bool                  page_loaded = false;
        bool                  total_pages_changed = false;
        HelioRetryController  retry_controller;

        for (int attempt = 1; attempt <= MAX_ATTEMPTS_PER_PAGE; ++attempt) {
            // Re-checked per attempt (not just per page): with up to 4 attempts and a
            // 100s HTTP timeout, a revoked run would otherwise keep issuing requests
            // under the old credential for minutes after a logout. The retry wait
            // happens at the end of the previous iteration, so this also covers the
            // "invalidated while sleeping" case.
            if (!is_run_current(run_generation)) {
                return false;
            }

            SupportDataHttpResponse response;
            try {
                response = fetcher(m_kind, page);
            } catch (const std::exception& e) {
                response.error = std::string("Helio support-data fetch failed: ") + e.what();
            } catch (...) {
                response.error = "Helio support-data fetch failed";
            }

            page_result = parse_support_data_page(m_kind, page, response);
            if (page_result.success && expected_total_pages != 0 &&
                page_result.total_pages != expected_total_pages) {
                // The catalog changed underneath the walk. Retrying *this* page is
                // futile — every otherwise-valid response would keep failing the same
                // comparison against the stale expectation until attempts run out.
                // Restart the walk instead (handled below).
                page_result.success = false;
                page_result.retry_kind = HelioRetryKind::Transient;
                page_result.error = "Helio support-data total page count changed during pagination";
                total_pages_changed = true;
                break;
            }
            if (page_result.success) {
                page_loaded = true;
                break;
            }

            const bool will_retry = attempt < MAX_ATTEMPTS_PER_PAGE &&
                                    retry_controller.should_retry(page_result.retry_kind);
            SupportDataLoadAttempt log_entry;
            log_entry.kind         = m_kind;
            log_entry.page         = page;
            log_entry.attempt      = attempt;
            log_entry.max_attempts = MAX_ATTEMPTS_PER_PAGE;
            log_entry.status       = page_result.status;
            log_entry.retry_kind   = page_result.retry_kind;
            log_entry.will_retry   = will_retry;
            log_entry.error        = page_result.error;
            log_entry.trace_id     = page_result.trace_id;
            log_attempt(logger, log_entry);

            if (!will_retry) {
                break;
            }

            if (sleeper) {
                try {
                    sleeper(attempt * 2);
                } catch (const std::exception& e) {
                    page_result.error = std::string("Helio support-data retry wait failed: ") + e.what();
                    break;
                } catch (...) {
                    page_result.error = "Helio support-data retry wait failed";
                    break;
                }
            }
        }

        if (total_pages_changed) {
            SupportDataLoadAttempt log_entry;
            log_entry.kind         = m_kind;
            log_entry.page         = page;
            log_entry.attempt      = MAX_PAGINATION_RESTARTS - restarts_remaining + 1;
            log_entry.max_attempts = MAX_PAGINATION_RESTARTS;
            log_entry.status       = page_result.status;
            log_entry.retry_kind   = page_result.retry_kind;
            log_entry.will_retry   = restarts_remaining > 0;
            log_entry.error        = page_result.error;
            log_entry.trace_id     = page_result.trace_id;
            log_attempt(logger, log_entry);

            if (restarts_remaining <= 0) {
                fail("Helio support-data total page count kept changing during pagination", run_generation);
                return false;
            }
            --restarts_remaining;
            staging.clear();
            page                 = 1;
            expected_total_pages = 0;
            continue;
        }

        if (!page_loaded) {
            fail(page_result.error.empty() ? "Helio support-data request failed" : std::move(page_result.error),
                 run_generation);
            return false;
        }

        if (expected_total_pages == 0) {
            expected_total_pages = page_result.total_pages;
        }
        staging.insert(staging.end(),
                       std::make_move_iterator(page_result.items.begin()),
                       std::make_move_iterator(page_result.items.end()));

        if (!page_result.has_next_page) {
            break;
        }
        ++page;
    }

    if (staging.empty()) {
        fail("Helio support-data response contained no supported entries", run_generation);
        return false;
    }

    publish(std::move(staging), run_generation);
    return is_run_current(run_generation);
}

void SupportDataCatalogStore::publish(std::vector<HelioSupportedData>&& complete_snapshot,
                                      std::uint64_t                    run_generation)
{
    auto snapshot = std::make_shared<const std::vector<HelioSupportedData>>(std::move(complete_snapshot));

    std::lock_guard<std::mutex> lock(m_mutex);
    if (run_generation != m_generation) {
        // The store was invalidated while this run was in flight; its data belongs to
        // credentials that are no longer current, so drop it and keep the store reset.
        return;
    }
    m_snapshot    = std::move(snapshot);
    m_state       = SupportDataLoadState::Ready;
    m_last_error.clear();
    m_run_claimed = false;
}

void SupportDataCatalogStore::fail(std::string error, std::uint64_t run_generation)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (run_generation != m_generation) {
        return;
    }
    m_state       = SupportDataLoadState::Failed;
    m_last_error  = std::move(error);
    m_run_claimed = false;
}

SupportDataLoadState SupportDataCatalogStore::state() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_state;
}

SupportDataCatalogStore::Snapshot SupportDataCatalogStore::snapshot() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_snapshot;
}

std::string SupportDataCatalogStore::last_error() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_last_error;
}

bool SupportDataCatalogStore::has_usable_snapshot() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_snapshot && !m_snapshot->empty();
}

SupportDataCatalogView SupportDataCatalogStore::view() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return {m_state, m_snapshot, m_last_error};
}

} // namespace Slic3r
