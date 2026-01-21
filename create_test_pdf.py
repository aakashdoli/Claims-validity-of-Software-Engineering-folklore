from reportlab.pdfgen import canvas

def create_pdf(filename):
    c = canvas.Canvas(filename)
    c.setFont("Helvetica", 12)
    
    text_content = [
        "Chapter 1: Organizational Structure",
        "",
        "In 1967, Melvin Conway introduced an idea that has henceforth been known as Conway's Law.",
        "It states that organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations.",
        "This is often summarized as: 'Any piece of software reflects the organizational structure that produced it.'",
        "",
        "Another common belief in the industry is that Test-Driven Development (TDD) significantly reduces bug density.",
        "According to a study by Microsoft Research [1], TDD can increase development time by 15% to 35%, but checks regarding quality were consistent.",
        "However, some developers simply claim that 'Clean Code makes your code run faster', which is largely considered folklore without empirical backing.",
        "",
        "References:",
        "[1] N. Nagappan et al., 'Realizing quality improvement through test driven development: results and experiences of four industrial teams', Empir Software Eng, 2008."
    ]
    
    y = 800
    for line in text_content:
        c.drawString(50, y, line)
        y -= 20
        
    c.save()

if __name__ == "__main__":
    create_pdf("test_conway.pdf")
    print("Created test_conway.pdf")
