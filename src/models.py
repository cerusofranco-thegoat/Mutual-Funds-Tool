"""Pydantic data models for structured output from Claude API and internal data flow."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# --- Document ingestion models ---

class PageContent(BaseModel):
    """Raw content extracted from a single page."""
    page_number: int
    text: str
    tables: list[list[list[str]]] = Field(default_factory=list, description="Tables as list of rows of cells")


class DocumentContent(BaseModel):
    """All content extracted from a single input file."""
    filename: str
    pages: list[PageContent]


# --- Fund identification (Claude Call 1) ---

class FundIdentification(BaseModel):
    """A single fund identified from a prospectus document."""
    fund_name: str = Field(description="Full legal name of the fund as written in the document")
    date: Optional[str] = Field(default=None, description="Prospectus date (YYYY-MM-DD or as written)")
    fund_type: Optional[str] = Field(default=None, description="Fund type: renta variable, deuda, cobertura, etc.")
    company: Optional[str] = Field(default=None, description="Management company (e.g., BlackRock Mexico)")
    page_start: Optional[int] = Field(default=None, description="First page of this fund's content")
    page_end: Optional[int] = Field(default=None, description="Last page of this fund's content")


class FundIdentificationResult(BaseModel):
    """All funds identified in a single document."""
    funds: list[FundIdentification]


# --- Risk extraction (Claude Call 2) ---

class RiskItem(BaseModel):
    """A single risk factor extracted from the prospectus."""
    category: str = Field(description="Risk category: market, credit, liquidity, operational, counterparty, etc.")
    description: str = Field(description="1-2 sentence summary of the risk in English")
    severity: Optional[str] = Field(default=None, description="Low, Medium, High if determinable")


class ValueAtRisk(BaseModel):
    """Value at Risk metric."""
    value: Optional[float] = Field(default=None, description="VaR numeric value (percentage)")
    period: Optional[str] = Field(default=None, description="Time period (e.g., 1 day, 1 month)")
    confidence_level: Optional[float] = Field(default=None, description="Confidence level (e.g., 95, 97.5)")


class FundRisks(BaseModel):
    """All risk information extracted for a fund."""
    var: Optional[ValueAtRisk] = None
    risk_items: list[RiskItem] = Field(default_factory=list)
    risk_summary: Optional[str] = Field(default=None, description="Overall risk summary in English")


# --- Returns extraction (Claude Call 3) ---

class PeriodReturn(BaseModel):
    """Return for a specific time period."""
    period: str = Field(description="Time period label: 1M, 3M, 6M, 1Y, 3Y, YTD, Since Inception, etc.")
    value: Optional[float] = Field(default=None, description="Return value as percentage")


class SeriesReturn(BaseModel):
    """Returns for a specific investor series/class."""
    series_name: str = Field(description="Series/class name (e.g., Serie A, Serie B, Serie F)")
    returns: list[PeriodReturn] = Field(default_factory=list)


class BenchmarkReturn(BaseModel):
    """Benchmark comparison returns."""
    benchmark_name: str
    returns: list[PeriodReturn] = Field(default_factory=list)


class FundReturns(BaseModel):
    """All return information for a fund."""
    series: list[SeriesReturn] = Field(default_factory=list)
    benchmarks: list[BenchmarkReturn] = Field(default_factory=list)


# --- Portfolio extraction (Claude Call 4) ---

class PortfolioHolding(BaseModel):
    """A single holding in the fund's investment portfolio."""
    asset_name: str = Field(description="Name of the asset/security")
    asset_type: Optional[str] = Field(default=None, description="Government bond, corporate bond, equity, derivative, etc.")
    issuer: Optional[str] = Field(default=None, description="Issuer of the security")
    percentage: Optional[float] = Field(default=None, description="Percentage of total portfolio")
    market_value: Optional[float] = Field(default=None, description="Market value in local currency")
    currency: Optional[str] = Field(default=None, description="Currency (MXN, USD, etc.)")
    maturity_date: Optional[str] = Field(default=None, description="Maturity date if applicable")
    credit_rating: Optional[str] = Field(default=None, description="Credit rating if available")
    coupon_rate: Optional[float] = Field(default=None, description="Coupon rate if applicable")


class FundPortfolio(BaseModel):
    """Complete investment portfolio for a fund."""
    holdings: list[PortfolioHolding] = Field(default_factory=list)
    total_assets: Optional[float] = Field(default=None, description="Total net assets of the fund")
    total_assets_currency: Optional[str] = Field(default=None, description="Currency of total assets")


# --- Complete fund data ---

class FundData(BaseModel):
    """All extracted data for a single fund."""
    identification: FundIdentification
    risks: Optional[FundRisks] = None
    returns: Optional[FundReturns] = None
    portfolio: Optional[FundPortfolio] = None
    source_file: str = ""


# --- Analytical assessment (Claude Call 5) ---

class AssetDistribution(BaseModel):
    """Distribution of a single asset type across all funds."""
    asset_type: str
    count: int = 0
    total_value: Optional[float] = None
    percentage: Optional[float] = None


class GoNoGoDecision(BaseModel):
    """Go/No-Go decision for a single fund."""
    fund_name: str
    decision: str = Field(description="Go, No-Go, or Conditional")
    justification: str


class RiskToleranceAlignment(BaseModel):
    """Risk tolerance assessment for a fund across investor profiles."""
    fund_name: str
    conservative: str = Field(description="Suitable, Marginal, or Unsuitable")
    moderate: str = Field(description="Suitable, Marginal, or Unsuitable")
    aggressive: str = Field(description="Suitable, Marginal, or Unsuitable")
    rationale: Optional[str] = None


class CapitalSizing(BaseModel):
    """Capital allocation recommendation for a fund."""
    fund_name: str
    recommended_pct: Optional[float] = Field(default=None, description="Recommended allocation percentage")
    min_pct: Optional[float] = None
    max_pct: Optional[float] = None
    rationale: Optional[str] = None


class DiversificationCheck(BaseModel):
    """A single diversification metric or finding."""
    metric: str
    status: str = Field(description="Pass, Warning, or Fail")
    details: str


class InvestmentHorizon(BaseModel):
    """Investment horizon classification for a fund."""
    fund_name: str
    horizon: str = Field(description="Short-term, Medium-term, or Long-term")
    rationale: str


class ValueAssessment(BaseModel):
    """Value assessment for a fund."""
    fund_name: str
    fee_level: Optional[str] = Field(default=None, description="Low, Medium, or High")
    return_risk_ratio: Optional[str] = None
    fair_value: str = Field(description="Yes, No, or Borderline")
    rationale: Optional[str] = None


class FundApproval(BaseModel):
    """Final approval status for a fund."""
    fund_name: str
    status: str = Field(description="Approved, Conditional, or Rejected")
    conditions: Optional[str] = Field(default=None, description="Conditions if status is Conditional")


class FundInvestmentSummary(BaseModel):
    """Summary of a fund's key investment metrics."""
    fund_name: str
    total_aum: Optional[float] = None
    aum_currency: Optional[str] = None
    num_holdings: Optional[int] = None
    avg_return_1y: Optional[float] = None


class AnalyticalReport(BaseModel):
    """Complete cross-fund analytical report."""
    asset_distribution: list[AssetDistribution] = Field(default_factory=list)
    fund_summaries: list[FundInvestmentSummary] = Field(default_factory=list)
    go_nogo_decisions: list[GoNoGoDecision] = Field(default_factory=list)
    risk_tolerance: list[RiskToleranceAlignment] = Field(default_factory=list)
    capital_sizing: list[CapitalSizing] = Field(default_factory=list)
    diversification_checks: list[DiversificationCheck] = Field(default_factory=list)
    investment_horizons: list[InvestmentHorizon] = Field(default_factory=list)
    value_assessments: list[ValueAssessment] = Field(default_factory=list)
    fund_approvals: list[FundApproval] = Field(default_factory=list)
    overall_summary: Optional[str] = Field(default=None, description="High-level summary of all findings")
