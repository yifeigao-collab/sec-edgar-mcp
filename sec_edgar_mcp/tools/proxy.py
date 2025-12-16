from typing import Any
from ..core.client import EdgarClient
from ..utils.exceptions import FilingNotFoundError
from .types import ToolResponse


class ProxyTools:
    """Tools for proxy statement (DEF 14A) operations."""

    def __init__(self):
        self.client = EdgarClient()

    def get_proxy_statement(
        self, identifier: str, accession_number: str | None = None
    ) -> ToolResponse:
        """
        Get structured proxy statement data from a DEF 14A filing.

        Extracts executive compensation, pay vs performance metrics,
        and governance data using the SEC's Executive Compensation Disclosure taxonomy.
        """
        try:
            company = self.client.get_company(identifier)

            # Find the proxy statement filing
            # Prioritize DEF 14A (full proxy) over DEFA14A (supplemental materials)
            # as DEF 14A contains XBRL data while DEFA14A typically does not
            primary_proxy_forms = ["DEF 14A", "DEF 14A/A"]
            all_proxy_forms = ["DEF 14A", "DEF 14A/A", "DEFA14A", "DEFM14A"]
            filing = None

            if accession_number:
                # Find specific filing by accession number
                for f in company.get_filings(form=all_proxy_forms):
                    if f.accession_number.replace("-", "") == accession_number.replace(
                        "-", ""
                    ):
                        filing = f
                        break
                if not filing:
                    raise FilingNotFoundError(
                        f"Proxy statement with accession {accession_number} not found"
                    )
            else:
                # First try to get the latest DEF 14A (full proxy with XBRL)
                filings = company.get_filings(form=primary_proxy_forms)
                filing = filings.latest() if filings else None

                # Fall back to any proxy form if no DEF 14A found
                if not filing:
                    filings = company.get_filings(form=all_proxy_forms)
                    filing = filings.latest() if filings else None

                if not filing:
                    return {
                        "success": False,
                        "error": "No proxy statement (DEF 14A) filings found for this company",
                    }

            # Get the ProxyStatement object
            proxy = filing.obj()

            if not proxy:
                return {
                    "success": False,
                    "error": "Could not parse proxy statement data",
                    "filing_info": {
                        "form_type": filing.form,
                        "filing_date": str(filing.filing_date),
                        "accession_number": filing.accession_number,
                    },
                }

            # Build the result
            result: dict[str, Any] = {
                "success": True,
                "cik": company.cik,
                "name": company.name,
                "filing_reference": {
                    "form_type": filing.form,
                    "filing_date": (
                        filing.filing_date.isoformat()
                        if hasattr(filing.filing_date, "isoformat")
                        else str(filing.filing_date)
                    ),
                    "accession_number": filing.accession_number,
                    "sec_url": f"https://www.sec.gov/Archives/edgar/data/{company.cik}/{filing.accession_number.replace('-', '')}/{filing.accession_number}.txt",
                    "filing_url": filing.url if hasattr(filing, "url") else None,
                    "data_source": f"SEC EDGAR Filing {filing.accession_number}, extracted directly from DEF 14A XBRL data",
                    "disclaimer": "All data extracted directly from SEC EDGAR filing. No estimates or calculations added.",
                },
            }

            # Extract basic info
            if hasattr(proxy, "company_name"):
                result["company_name"] = proxy.company_name
            if hasattr(proxy, "fiscal_year_end"):
                result["fiscal_year_end"] = proxy.fiscal_year_end
            if hasattr(proxy, "filing_date"):
                result["proxy_filing_date"] = proxy.filing_date

            # Check if XBRL data is available
            result["has_xbrl"] = getattr(proxy, "has_xbrl", False)

            if not result["has_xbrl"]:
                result["note"] = (
                    "No XBRL data available. Executive compensation data requires XBRL "
                    "(not available for Smaller Reporting Companies, Emerging Growth Companies, SPACs, or funds)."
                )
                return result

            # Extract executive compensation data
            executive_comp = {}

            # CEO (PEO - Principal Executive Officer) info
            if hasattr(proxy, "peo_name"):
                executive_comp["ceo_name"] = proxy.peo_name
            if hasattr(proxy, "peo_total_comp"):
                executive_comp["ceo_total_compensation"] = (
                    float(proxy.peo_total_comp) if proxy.peo_total_comp else None
                )
            if hasattr(proxy, "peo_actually_paid_comp"):
                executive_comp["ceo_actually_paid_compensation"] = (
                    float(proxy.peo_actually_paid_comp)
                    if proxy.peo_actually_paid_comp
                    else None
                )

            # Other Named Executive Officers (NEO) average
            if hasattr(proxy, "neo_avg_total_comp"):
                executive_comp["neo_avg_total_compensation"] = (
                    float(proxy.neo_avg_total_comp)
                    if proxy.neo_avg_total_comp
                    else None
                )
            if hasattr(proxy, "neo_avg_actually_paid_comp"):
                executive_comp["neo_avg_actually_paid_compensation"] = (
                    float(proxy.neo_avg_actually_paid_comp)
                    if proxy.neo_avg_actually_paid_comp
                    else None
                )

            if executive_comp:
                result["executive_compensation"] = executive_comp

            # Extract pay vs performance data
            pvp_data = {}
            if hasattr(proxy, "total_shareholder_return"):
                pvp_data["total_shareholder_return"] = (
                    float(proxy.total_shareholder_return)
                    if proxy.total_shareholder_return
                    else None
                )
            if hasattr(proxy, "peer_group_tsr"):
                pvp_data["peer_group_tsr"] = (
                    float(proxy.peer_group_tsr) if proxy.peer_group_tsr else None
                )
            if hasattr(proxy, "net_income"):
                pvp_data["net_income"] = (
                    float(proxy.net_income) if proxy.net_income else None
                )

            if pvp_data:
                result["pay_vs_performance"] = pvp_data

            # Extract executive compensation DataFrame if available
            if (
                hasattr(proxy, "executive_compensation")
                and proxy.executive_compensation is not None
            ):
                try:
                    df = proxy.executive_compensation
                    if hasattr(df, "to_dict"):
                        result["executive_compensation_history"] = df.to_dict(
                            orient="records"
                        )
                except Exception:
                    pass

            # Extract named executives list if available
            if hasattr(proxy, "named_executives") and proxy.named_executives:
                try:
                    named_execs = []
                    for exec_info in proxy.named_executives:
                        exec_dict = {}
                        if hasattr(exec_info, "name"):
                            exec_dict["name"] = exec_info.name
                        if hasattr(exec_info, "title"):
                            exec_dict["title"] = exec_info.title
                        if hasattr(exec_info, "total_compensation"):
                            exec_dict["total_compensation"] = (
                                float(exec_info.total_compensation)
                                if exec_info.total_compensation
                                else None
                            )
                        if exec_dict:
                            named_execs.append(exec_dict)
                    if named_execs:
                        result["named_executives"] = named_execs
                except Exception:
                    pass

            return result

        except FilingNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get proxy statement: {str(e)}",
            }

    def get_executive_compensation(self, identifier: str) -> ToolResponse:
        """
        Get executive compensation summary from the latest proxy statement.

        This is a convenience method that focuses on executive compensation data.
        """
        result = self.get_proxy_statement(identifier)

        if not result.get("success"):
            return result

        # Extract just the compensation-related fields
        compensation_result: dict[str, Any] = {
            "success": True,
            "cik": result.get("cik"),
            "name": result.get("name"),
            "filing_reference": result.get("filing_reference"),
            "has_xbrl": result.get("has_xbrl", False),
        }

        if result.get("note"):
            compensation_result["note"] = result["note"]

        if result.get("executive_compensation"):
            compensation_result["executive_compensation"] = result[
                "executive_compensation"
            ]

        if result.get("named_executives"):
            compensation_result["named_executives"] = result["named_executives"]

        if result.get("executive_compensation_history"):
            compensation_result["executive_compensation_history"] = result[
                "executive_compensation_history"
            ]

        return compensation_result
