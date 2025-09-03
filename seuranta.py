import streamlit as st
import yfinance as yf
import pandas as pd
import altair as alt
import json
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
from datetime import date

PORTFOLIO_FILE = "portfolios.json"

### Tiedostonhallintafunktiot ###

def load_portfolios():
    """Lataa salkkutiedot portfolios.json-tiedostosta."""
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, 'r') as f:
            portfolios = json.load(f)
            for portfolio_name in portfolios:
                for asset in portfolios[portfolio_name]:
                    if 'shares' in asset:
                        asset['shares'] = float(asset['shares'])
                    if 'buy_price' in asset:
                        asset['buy_price'] = float(asset['buy_price'])
                    if 'target_percentage' in asset:
                        asset['target_percentage'] = float(asset['target_percentage'])
            return portfolios
    return {}

def save_portfolios(portfolios):
    """Tallentaa salkkutiedot portfolios.json-tiedostoon."""
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(portfolios, f, indent=4)

def delete_portfolio(portfolio_name, portfolios):
    """Poistaa salkun pysyvästi."""
    if portfolio_name in portfolios:
        del portfolios[portfolio_name]
        save_portfolios(portfolios)
        st.success(f"Salkku '{portfolio_name}' poistettu.")

### Tietojen hakeminen ja laskeminen ###

def get_stock_data(tickers):
    """Hakee osakkeiden nykyiset hinnat Yahoo Financesta."""
    data = {}
    if not tickers:
        return data
    try:
        downloaded_data = yf.download(tickers, period="1d")
        if 'Adj Close' in downloaded_data.columns:
            if isinstance(downloaded_data['Adj Close'], pd.DataFrame):
                data = downloaded_data['Adj Close'].iloc[-1].to_dict()
            else:
                data = downloaded_data['Adj Close'].to_dict()
        elif 'Close' in downloaded_data.columns:
            if isinstance(downloaded_data['Close'], pd.DataFrame):
                data = downloaded_data['Close'].iloc[-1].to_dict()
            else:
                data = downloaded_data['Close'].to_dict()
    except Exception:
        for ticker in tickers:
            try:
                ticker_obj = yf.Ticker(ticker)
                hist = ticker_obj.history(period="1d")
                if not hist.empty:
                    if 'Adj Close' in hist.columns:
                        data[ticker] = hist['Adj Close'][0]
                    elif 'Close' in hist.columns:
                        data[ticker] = hist['Close'][0]
                else:
                    st.warning(f"Tyhjä historiallinen data symbolille: {ticker}")
            except Exception:
                pass
    return data

def calculate_portfolio_metrics(assets, current_prices):
    """Laskee salkun tuoton ja muut mittarit."""
    portfolio_data = []
    total_current_value = 0
    total_original_cost = 0

    for asset in assets:
        name = asset.get("name", "Nimetön")
        ticker = asset.get("ticker", "Tuntematon")
        buy_price = asset.get("buy_price")
        shares = asset.get("shares")
        currency = asset.get("currency", "EUR")
        buy_currency_rate = asset.get("buy_currency_rate", 1.0)
        current_currency_rate = asset.get("current_currency_rate", 1.0)
        target_percentage = asset.get("target_percentage", 0.0)
        
        current_price = None
        if asset.get('is_manual'):
            current_price = asset.get('manual_price')
        elif ticker in current_prices:
            current_price = current_prices[ticker]
        
        if current_price is None:
            continue
            
        original_cost_eur = (buy_price * shares) / buy_currency_rate
        current_value_eur = (current_price * shares) / current_currency_rate
        
        profit_eur = current_value_eur - original_cost_eur
        profit_percent = (profit_eur / original_cost_eur) * 100 if original_cost_eur != 0 else 0
        
        total_original_cost += original_cost_eur
        total_current_value += current_value_eur
        
        unique_id = f"{name} ({ticker})"
        
        portfolio_data.append({
            "Kohde": unique_id,
            "Alkuperäinen Nimi": name,
            "Ticker": ticker,
            "Ostohinta": f"{buy_price:.2f} {currency}",
            "Nykyinen hinta": f"{current_price:.2f} {currency}",
            "Osuudet": shares,
            "Alkuperäinen arvo": original_cost_eur,
            "Nykyinen arvo": current_value_eur,
            "Tuotto (€)": profit_eur,
            "Tuotto (%)": profit_percent,
            "Tavoite (%)": target_percentage
        })
    
    df = pd.DataFrame(portfolio_data)
    
    total_profit = total_current_value - total_original_cost
    total_profit_percent = (total_profit / total_original_cost) * 100 if total_original_cost != 0 else 0
    total_row = pd.DataFrame([{
        "Kohde": "Kokonaisalkku",
        "Tuotto (€)": total_profit,
        "Tuotto (%)": total_profit_percent,
        "Alkuperäinen arvo": total_original_cost,
        "Nykyinen arvo": total_current_value,
        "Tavoite (%)": 100.0
    }])
    
    if total_current_value > 0:
        df['Osuus salkusta (%)'] = (df['Nykyinen arvo'] / total_current_value) * 100
        df['Poikkeama (%)'] = df.apply(lambda row: row['Osuus salkusta (%)'] - row['Tavoite (%)'] if row['Tavoite (%)'] > 0 else 0.0, axis=1)
        df['Poikkeama (€)'] = df.apply(lambda row: row['Nykyinen arvo'] - (row['Tavoite (%)'] / 100 * total_current_value) if row['Tavoite (%)'] > 0 else 0.0, axis=1)
    else:
        df['Osuus salkusta (%)'] = 0
        df['Poikkeama (%)'] = 0
        df['Poikkeama (€)'] = 0

    return df, total_row

def display_portfolio_summary(df, total_row, portfolio_name):
    """Näyttää salkun yhteenvedon ja erittelyn Streamlit-käyttöliittymässä."""
    if df.empty:
        st.info("Salkku on tyhjä. Lisää sijoituskohteita muokataksesi.")
        return
        
    st.subheader(f"Yhteenveto: {portfolio_name}")
    
    total_current_value = total_row["Nykyinen arvo"].iloc[0]
    total_profit = total_row["Tuotto (€)"].iloc[0]
    total_profit_percent = total_row["Tuotto (%)"].iloc[0]
    
    st.metric(label="Salkun kokonaisarvo", value=f"{total_current_value:.2f} €", delta=f"{total_profit:.2f} € ({total_profit_percent:.2f} %)")
    
    st.subheader("Sijoitusten jakauma")
    pie_chart_data = df.groupby("Kohde")["Nykyinen arvo"].sum()
    df_pie = pd.DataFrame({"Kohteet": pie_chart_data.index, "Arvot": pie_chart_data.values})
    df_pie['Prosentit'] = df_pie['Arvot'] / df_pie['Arvot'].sum()
    
    custom_color_scale = alt.Scale(range=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#a6cee3', '#b2df8a', '#fb9a99', '#fdbf6f', '#cab2d6', '#ffff99'])
    
    pie_chart = alt.Chart(df_pie).mark_arc(outerRadius=120).encode(
        theta=alt.Theta("Arvot", stack=True),
        color=alt.Color("Kohteet", scale=custom_color_scale),
        tooltip=["Kohteet", alt.Tooltip("Arvot", format=".2f", title="Nykyinen arvo €"), alt.Tooltip("Prosentit", format=".1%", title="Osuus")]
    )
    st.altair_chart(pie_chart, use_container_width=True)

    st.subheader("Sijoituskohteiden erittely")
    def color_profit(val):
        """Värjää solun sisällön tuoton perusteella."""
        if isinstance(val, (int, float)):
            color = 'red' if val < 0 else 'green'
            return f'color: {color}'
        return ''
        
    def color_deviation(val):
        """Värjää poikkeaman solun, jos se ylittää 5 % toleranssin."""
        if isinstance(val, (int, float)):
            if abs(val) > 5.0:
                return f'color: red; font-weight: bold;'
        return ''
    
    display_df = df.rename(columns={"Alkuperäinen Nimi": "Nimi"})
    display_df = display_df[["Nimi", "Alkuperäinen arvo", "Nykyinen arvo", "Tuotto (€)", "Tuotto (%)", "Osuus salkusta (%)", "Tavoite (%)", "Poikkeama (%)", "Poikkeama (€)"]]
    st.dataframe(display_df.style.applymap(color_profit, subset=['Tuotto (€)', 'Tuotto (%)']).applymap(color_deviation, subset=['Poikkeama (%)']).format(
        {
            "Alkuperäinen arvo": "€ {:.2f}", 
            "Nykyinen arvo": "€ {:.2f}",
            "Tuotto (€)": "€ {:.2f}",
            "Tuotto (%)": "{:.2f} %",
            "Osuus salkusta (%)": "{:.2f} %",
            "Tavoite (%)": "{:.2f} %",
            "Poikkeama (%)": "{:.2f} %",
            "Poikkeama (€)": "€ {:.2f}"
        },
        na_rep="-"
    ))
    
    st.subheader("Tuotto kohteittain")
    chart_data = pd.concat([total_row, df])
    
    bar_chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X('Kohde', sort=None),
        y=alt.Y('Tuotto (€)', title="Tuotto (€)"),
        tooltip=['Kohde', alt.Tooltip('Tuotto (€)', format='.2f')],
        color=alt.condition(
            alt.datum['Tuotto (€)'] > 0,
            alt.value('green'),
            alt.value('red')
        )
    ).properties(
        title="Salkun tuotto kohteittain ja kokonaisuutena"
    )
    st.altair_chart(bar_chart, use_container_width=True)
    st.markdown("---")

def create_pdf_report(df, total_row, portfolio_name):
    """Luo ja muotoilee salkusta PDF-raportin."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    today = date.today().strftime("%d.%m.%Y")
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontSize=16,
        leading=20
    )
    heading2_style = ParagraphStyle(
        'Heading2Style',
        parent=styles['h2'],
        fontSize=12,
        leading=15
    )
    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=12
    )

    elements.append(Paragraph(f"Salkun '{portfolio_name}' raportti - {today}", title_style))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("Sijoituskohteiden erittely", heading2_style))
    
    raportti_df = df.rename(columns={"Alkuperäinen Nimi": "Nimi"})
    raportti_df = raportti_df[["Nimi", "Alkuperäinen arvo", "Nykyinen arvo", "Tuotto (€)", "Tuotto (%)", "Osuus salkusta (%)", "Tavoite (%)", "Poikkeama (%)", "Poikkeama (€)"]]
    
    table_data = [[Paragraph(col, normal_style) for col in raportti_df.columns.tolist()]]
    for _, row in raportti_df.iterrows():
        row_list = []
        for col in raportti_df.columns.tolist():
            val = row[col]
            if col == 'Nimi':
                 row_list.append(Paragraph(str(val), normal_style))
            elif col in ['Alkuperäinen arvo', 'Nykyinen arvo']:
                row_list.append(Paragraph(f"{val:.2f}", normal_style))
            elif col == 'Osuus salkusta (%)':
                row_list.append(Paragraph(f"{val:.2f} %", normal_style))
            elif col == 'Tavoite (%)':
                row_list.append(Paragraph(f"{val:.2f} %", normal_style) if not pd.isna(val) else Paragraph("-", normal_style))
            elif col in ['Tuotto (€)', 'Tuotto (%)']:
                color = 'green' if val >= 0 else 'red'
                if col == 'Tuotto (%)':
                    text = f"{val:.2f} %"
                else:
                    text = f"{val:.2f}"
                row_list.append(Paragraph(f'<font color="{color}">{text}</font>', normal_style))
            elif col == 'Poikkeama (%)':
                if isinstance(val, (int, float)):
                    color = 'red' if abs(val) > 5.0 else 'black'
                    text = f"{val:.2f} %"
                    row_list.append(Paragraph(f'<font color="{color}">{text}</font>', normal_style))
                else:
                    row_list.append(Paragraph("-", normal_style))
            elif col == 'Poikkeama (€)':
                if isinstance(val, (int, float)):
                    text = f"{val:.2f}"
                    row_list.append(Paragraph(f'{text}', normal_style))
                else:
                    row_list.append(Paragraph("-", normal_style))
        table_data.append(row_list)
        
    total_original_cost = total_row["Alkuperäinen arvo"].iloc[0]
    total_current_value = total_row["Nykyinen arvo"].iloc[0]
    total_profit = total_row["Tuotto (€)"].iloc[0]
    total_profit_percent = total_row["Tuotto (%)"].iloc[0]

    total_row_data = [
        Paragraph("Kokonaisalkku", normal_style),
        Paragraph(f"{total_original_cost:.2f}", normal_style),
        Paragraph(f"{total_current_value:.2f}", normal_style),
        Paragraph(f'<font color="{("green" if total_profit >= 0 else "red")}">{total_profit:.2f}</font>', normal_style),
        Paragraph(f'<font color="{("green" if total_profit_percent >= 0 else "red")}">{total_profit_percent:.2f} %</font>', normal_style),
        Paragraph("100.00 %", normal_style),
        Paragraph("-", normal_style),
        Paragraph("-", normal_style),
        Paragraph("-", normal_style)
    ]
    table_data.append(total_row_data)
    
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ])

    table = Table(table_data)
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def main():
    st.title("Sijoitussalkun seuranta 📊")
    
    portfolios = load_portfolios()
    
    st.sidebar.header("Hallitse salkkuja")
    portfolio_names = sorted(list(portfolios.keys()))
    
    if "selected_portfolio" not in st.session_state:
        st.session_state.selected_portfolio = "Uusi salkku"
    
    current_index = 0
    if st.session_state.selected_portfolio in portfolio_names:
        current_index = portfolio_names.index(st.session_state.selected_portfolio) + 1
        
    selected_portfolio_name = st.sidebar.selectbox("Valitse salkku", ["Uusi salkku"] + portfolio_names, index=current_index)
    
    if selected_portfolio_name != st.session_state.selected_portfolio:
        st.session_state.selected_portfolio = selected_portfolio_name
        st.rerun() # Korvattu st.experimental_rerun()
    
    current_assets = []
    if selected_portfolio_name == "Uusi salkku":
        st.subheader("Uusi salkku")
        new_portfolio_name = st.text_input("Anna uuden salkun nimi:")
        if st.button("Luo uusi salkku"):
            if new_portfolio_name in portfolios:
                st.error("Salkku tällä nimellä on jo olemassa.")
            else:
                portfolios[new_portfolio_name] = []
                save_portfolios(portfolios)
                st.success(f"Salkku '{new_portfolio_name}' luotu! Valitse se sivupalkista muokataksesi.")
                st.session_state.selected_portfolio = new_portfolio_name
                st.rerun() # Korvattu st.experimental_rerun()
        return
    else:
        current_assets = portfolios[selected_portfolio_name]
        st.subheader(f"Muokkaa salkkua: {selected_portfolio_name}")
        st.markdown("---")
    
    num_assets = st.number_input("Kuinka monta sijoituskohdetta sinulla on?", min_value=0, value=len(current_assets), step=1)
    
    assets = []
    for i in range(1, int(num_assets) + 1):
        st.subheader(f"Sijoituskohde {i}")
        asset_data = current_assets[i-1] if (i-1) < len(current_assets) else {}
        
        name = st.text_input(f"Syötä kohteen nimi:", value=asset_data.get('name', ''), key=f"name_{i}")
        ticker = st.text_input(f"Syötä osakkeen symboli:", value=asset_data.get('ticker', ''), key=f"ticker_{i}").upper()
        
        col1, col2 = st.columns(2)
        with col1:
            manual_input = st.checkbox("Manuaalinen syöttö", key=f"manual_{i}", value=asset_data.get('is_manual', False))
            if manual_input:
                manual_price = st.number_input(f"Syötä nykyinen hinta:", min_value=0.01, value=asset_data.get('manual_price', 0.01), key=f"manual_price_{i}")
                currency = st.selectbox("Valuutta:", ["EUR", "USD", "SEK", "GBP"], key=f"manual_currency_{i}", index=["EUR", "USD", "SEK", "GBP"].index(asset_data.get('currency', 'EUR')))
            else:
                manual_price = None
                currency = st.selectbox("Valuutta:", ["EUR", "USD", "SEK", "GBP"], key=f"currency_{i}", index=["EUR", "USD", "SEK", "GBP"].index(asset_data.get('currency', 'EUR')))

        with col2:
            buy_price = st.number_input(f"Syötä ostohinta:", min_value=0.01, value=asset_data.get('buy_price', 0.01), step=0.01, format="%.2f", key=f"buy_price_{i}")
            shares = st.number_input(f"Syötä omistettujen osuuksien määrä:", min_value=0.01, value=asset_data.get('shares', 1.0), step=0.01, format="%.2f", key=f"shares_{i}")
            buy_currency_rate = st.number_input(f"Ostokurssi (1 EUR = X {currency}):", min_value=0.01, value=asset_data.get('buy_currency_rate', 1.0), step=0.01, format="%.2f", key=f"buy_currency_rate_{i}", help="Syötä valuutan kurssi ostohetkellä suhteessa euroon.")
            current_currency_rate = st.number_input(f"Nykykurssi (1 EUR = X {currency}):", min_value=0.01, value=asset_data.get('current_currency_rate', 1.0), step=0.01, format="%.2f", key=f"current_currency_rate_{i}", help="Syötä valuutan kurssi tällä hetkellä suhteessa euroon.")
            
        target_percentage = st.number_input(f"Tavoiteosuus salkusta (%):", min_value=0.0, max_value=100.0, value=asset_data.get('target_percentage', 0.0), step=0.1, key=f"target_percentage_{i}")
            
        assets.append({
            "name": name, 
            "ticker": ticker, 
            "buy_price": buy_price, 
            "shares": shares, 
            "manual_price": manual_price, 
            "is_manual": manual_input, 
            "currency": currency, 
            "buy_currency_rate": buy_currency_rate, 
            "current_currency_rate": current_currency_rate, 
            "target_percentage": target_percentage
        })
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Tallenna muutokset salkkuun '{selected_portfolio_name}'"):
            portfolios[selected_portfolio_name] = assets
            save_portfolios(portfolios)
            st.success(f"Muutokset salkkuun '{selected_portfolio_name}' tallennettu!")
    with col2:
        if st.button(f"Poista salkku '{selected_portfolio_name}'"):
            delete_portfolio(selected_portfolio_name, portfolios)
            st.rerun() # Korvattu st.experimental_rerun()

    st.markdown("---")

    tab1, tab2 = st.tabs(["Salkun tarkastelu", "PDF-raportti"])

    with tab1:
        st.header("Salkun tarkastelu")
        if selected_portfolio_name != "Uusi salkku":
            if st.button(f"Tarkastele salkkua '{selected_portfolio_name}'"):
                st.write("Haetaan hintatiedot...")
                all_tickers = [asset['ticker'] for asset in portfolios[selected_portfolio_name] if not asset.get('is_manual') and asset.get('ticker')]
                current_prices = get_stock_data(list(set(all_tickers)))
                
                df, total_row = calculate_portfolio_metrics(portfolios[selected_portfolio_name], current_prices)
                display_portfolio_summary(df, total_row, selected_portfolio_name)
    
    with tab2:
        st.header("Luo PDF-raportti")
        st.write("Valitse salkku ja luo raportti ladattavaksi.")
        if selected_portfolio_name != "Uusi salkku" and st.button("Luo PDF-raportti", key="pdf_button"):
            all_tickers = [asset['ticker'] for asset in portfolios[selected_portfolio_name] if not asset.get('is_manual') and asset.get('ticker')]
            current_prices = get_stock_data(list(set(all_tickers)))
            
            df, total_row = calculate_portfolio_metrics(portfolios[selected_portfolio_name], current_prices)
            
            pdf_data = create_pdf_report(df, total_row, selected_portfolio_name)
            st.download_button(
                label="Lataa PDF-raportti",
                data=pdf_data,
                file_name=f"{selected_portfolio_name}_raportti.pdf",
                mime="application/pdf"
            )

if __name__ == "__main__":
    main()