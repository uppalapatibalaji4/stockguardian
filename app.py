                    # === HISTORICAL CHART (FIXED TZ) ===
                    if not data['history'].empty:
                        hist_df = data['history'].copy()
                        hist_df = hist_df.reset_index()
                        if 'Date' not in hist_df.columns:
                            hist_df = hist_df.rename(columns={hist_df.columns[0]: 'Date'})
                        hist_df['Date'] = hist_df['Date'].dt.strftime('%Y-%m-%d')
                        fig = px.line(hist_df, x='Date', y='Close', title=f"{inv['symbol']} 1Y Price")
                        fig.update_layout(xaxis_title="Date", yaxis_title="Price (₹)")
                        st.plotly_chart(fig, use_container_width=True)

                        # === 30-DAY FORECAST ===
                        forecast = forecast_with_prophet(data['history'])
                        if forecast is not None:
                            fig_forecast = px.line(forecast, x='ds', y='yhat', title="30-Day Forecast")
                            fig_forecast.add_scatter(x=forecast['ds'], y=forecast['yhat_lower'], name="Lower", line=dict(dash='dot'))
                            fig_forecast.add_scatter(x=forecast['ds'], y=forecast['yhat_upper'], name="Upper", line=dict(dash='dot'))
                            st.plotly_chart(fig_forecast, use_container_width=True)
                        
                        st.write(short_term_prediction(data['history']))
                    else:
                        st.write("No historical data.")
