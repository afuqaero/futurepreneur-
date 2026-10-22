# futurePreneur

## Business Readiness Platform

**Prototype for the UTM Programme**  
**Last updated:** 22 October 2026

futurePreneur is a practical business-readiness platform for micro and small-business owners. It helps a business owner understand where the business is today, learn useful business concepts, talk through challenges with an AI coach, and track progress over time.

The platform is designed for owners, not accountants. It turns business development into small, clear steps instead of overwhelming spreadsheets or theory.

## What it is used for

- A short Business Check-Up across eight core business areas
- Practical lessons for real small-business situations
- Downloadable templates and activities
- An AI Business Coach powered by DeepSeek
- Knowledge quizzes and scenario-based tests
- A progress view showing what to focus on next
- An administrator area for managing learning content and reviewing progress

## Prototype note

This is a working prototype created for the UTM Programme. Some areas are still being refined, and results should be treated as guidance rather than professional accounting, legal, or financial advice.

## Framework and services

- **Frontend:** HTML, CSS, and vanilla JavaScript
- **Backend:** Node.js serverless functions on Vercel
- **Database and authentication:** Supabase
- **AI coach:** DeepSeek API, accessed securely through the server
- **Hosting:** Vercel

The application is intentionally lightweight and responsive so it can be used from a laptop, tablet, or phone.

## Changelog — 22 October 2026

- Moved the production API to a native Node.js/Vercel serverless function.
- Connected the live coach to DeepSeek through a server-side API key.
- Added Supabase integration for authentication and business data.
- Fixed API routing so backend requests no longer fall through to the frontend page.
- Fixed the Vercel Node request/response handling that caused requests to hang.
- Improved the initial workspace loading experience with a quieter loading state.
- Corrected static image delivery for the dashboard illustration.
- Published the latest prototype to the Vercel production domain.

## Current status

The prototype includes all eight learning areas:

1. Business Strategy & Model
2. Marketing & Sales
3. Operations & Quality
4. Financial Management
5. People & Leadership
6. Systems & SOP
7. Legal & Risk
8. Digitalisation & Growth

The dashboard, check-up, learning area, coach, tests, progress view, and administration screens are available in the current prototype. Further work is focused on polishing the Supabase user journey, expanding content, and validating the experience with UTM Programme users.

## Links

- **Live prototype:** https://futurepreneur-ten.vercel.app
- **Repository:** https://github.com/nurhanisahiri-star/futurepreneur-.git

