#pragma once

#include "HelioRetryPolicy.hpp"

#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace Slic3r {

struct HelioSupportedData
{
    std::string id;
    std::string name;
    std::string native_name;
    std::string feedstock;
    bool        heated_chamber{false};
};

enum class SupportDataLoadState
{
    NotLoaded,
    Loading,
    Ready,
    Failed
};

enum class SupportDataCatalogKind
{
    Printers,
    Materials
};

struct SupportDataHttpResponse
{
    unsigned    status{0};
    std::string body;
    std::string error;
    std::string trace_id;
};

struct SupportDataPageResult
{
    bool                            success{false};
    bool                            has_next_page{false};
    int                             total_pages{0};
    unsigned                        status{0};
    HelioRetryKind                  retry_kind{HelioRetryKind::None};
    std::vector<HelioSupportedData> items;
    std::string                     error;
    std::string                     trace_id;
};

SupportDataPageResult parse_support_data_page(SupportDataCatalogKind       kind,
                                              int                          page,
                                              const SupportDataHttpResponse& response);

struct SupportDataCatalogView
{
    using Snapshot = std::shared_ptr<const std::vector<HelioSupportedData>>;

    SupportDataLoadState state{SupportDataLoadState::NotLoaded};
    Snapshot             snapshot;
    std::string          last_error;

    bool has_usable_snapshot() const noexcept { return snapshot && !snapshot->empty(); }
};

enum class SupportDataAvailability
{
    Usable,
    Synchronizing,
    LoadFailed
};

SupportDataAvailability support_data_availability(const SupportDataCatalogView& printers,
                                                  const SupportDataCatalogView& materials) noexcept;

struct SupportDataLoadAttempt
{
    SupportDataCatalogKind kind{SupportDataCatalogKind::Printers};
    int                    page{1};
    int                    attempt{1};
    int                    max_attempts{4};
    unsigned               status{0};
    HelioRetryKind         retry_kind{HelioRetryKind::None};
    bool                   will_retry{false};
    std::string            error;
    std::string            trace_id;
};

class SupportDataCatalogStore
{
public:
    using Snapshot     = SupportDataCatalogView::Snapshot;
    using PageFetcher  = std::function<SupportDataHttpResponse(SupportDataCatalogKind, int)>;
    using RetrySleeper = std::function<void(int)>;
    using Logger       = std::function<void(const SupportDataLoadAttempt&)>;

    static constexpr int MAX_ATTEMPTS_PER_PAGE = 4;

    explicit SupportDataCatalogStore(SupportDataCatalogKind kind);

    SupportDataCatalogStore(const SupportDataCatalogStore&) = delete;
    SupportDataCatalogStore& operator=(const SupportDataCatalogStore&) = delete;

    bool try_begin(bool force_refresh = false);

    // Returns true (and clears the flag) if a force-refresh was requested while a load
    // was already in flight (see try_begin()). Callers should use this to re-trigger a
    // fresh load with up-to-date credentials once the in-flight run completes, so a PAT
    // change that arrives mid-load is not silently dropped.
    bool consume_pending_refresh();
    bool has_pending_refresh() const;

    bool run(const PageFetcher&  fetcher,
             const RetrySleeper& sleeper = RetrySleeper(),
             const Logger&       logger = Logger());

    SupportDataCatalogKind kind() const noexcept { return m_kind; }
    SupportDataLoadState   state() const;
    Snapshot               snapshot() const;
    std::string            last_error() const;
    bool                   has_usable_snapshot() const;
    SupportDataCatalogView view() const;

private:
    bool claim_run();
    bool run_impl(const PageFetcher& fetcher, const RetrySleeper& sleeper, const Logger& logger);
    void publish(std::vector<HelioSupportedData>&& complete_snapshot);
    void fail(std::string error);

    const SupportDataCatalogKind m_kind;
    mutable std::mutex           m_mutex;
    SupportDataLoadState         m_state{SupportDataLoadState::NotLoaded};
    Snapshot                     m_snapshot;
    std::string                  m_last_error;
    bool                         m_run_claimed{false};
    bool                         m_pending_refresh{false};
};

} // namespace Slic3r
